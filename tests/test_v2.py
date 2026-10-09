from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from sqlalchemy import create_engine, text
from backend.db import SessionLocal
from backend.models import Inquiry, InquiryEvent, InquirySubmission, LoginSession, User, Order, OrderLine, now
from backend.security import digest
from backend.migrations import upgrade
from algorithms.procurement import greedy


def test_wishlist_version_rejects_stale_devices_and_legacy_writes(client, headers):
    body = {'sku_id': 1, 'room': '书房', 'quantity': 1}
    wish = client.post('/api/wishlist', headers=headers[2], json=body).json()
    path = f"/api/wishlist/{wish['id']}"
    assert client.post('/api/wishlist', headers=headers[2], json=body).status_code == 409
    assert client.patch(path, headers=headers[2], json={'quantity': 9}).status_code == 422
    saved = client.patch(path, headers=headers[2], json={'version': 1, 'quantity': 3})
    assert saved.status_code == 200 and saved.json()['version'] == 2
    assert client.patch(path, headers=headers[2], json={'version': 1, 'quantity': 9}).status_code == 409
    assert client.get('/api/wishlist', headers=headers[2]).json()[0]['quantity'] == 3


def test_inquiry_simultaneous_retry_creates_one_snapshot(client, headers):
    wish = client.post('/api/wishlist', headers=headers[2], json={'sku_id': 1}).json()
    body = {'wishlist_ids': [wish['id']], 'submission_key': 'inquiry-retry-2.0'}
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(pool.map(lambda _: client.post('/api/inquiries', headers=headers[2], json=body), range(2)))
    assert all(r.status_code == 201 for r in replies)
    assert replies[0].json()['id'] == replies[1].json()['id']
    assert client.post('/api/inquiries', headers=headers[2], json={**body, 'message': 'changed'}).status_code == 409
    with SessionLocal() as db:
        assert db.query(Inquiry).count() == db.query(InquirySubmission).count() == db.query(InquiryEvent).count() == 1


def test_wechat_binding_is_explicit_role_scoped_and_unique(client, headers, monkeypatch):
    from backend import wechat
    monkeypatch.setattr(wechat, 'exchange', lambda body: ('test-' + body.role, digest(body.code)))
    monkeypatch.setenv('WECHAT_MERCHANT_APP_ID', 'test-merchant')
    merchant = {'code': 'merchant-openid', 'role': 'merchant'}
    assert client.post('/api/auth/wechat', json=merchant).status_code == 409
    assert client.post('/api/auth/wechat/bind', headers=headers[2], json=merchant).status_code == 403
    assert client.post('/api/auth/wechat/bind', headers=headers[4], json=merchant).status_code == 200
    assert client.post('/api/auth/wechat/bind', headers=headers[5], json=merchant).status_code == 409
    result = client.post('/api/auth/wechat', json=merchant)
    assert result.status_code == 200 and result.json()['user']['id'] == 4
    assert client.get('/api/me/wechat', headers=headers[4]).json()['bound']
    with SessionLocal() as db:
        db.get(User, 4).active = False; db.commit()
    assert client.post('/api/auth/wechat', json=merchant).status_code == 403


def test_wechat_signup_requires_consent_and_provider_configuration(client, monkeypatch):
    from backend import wechat
    monkeypatch.delenv('WECHAT_APP_ID', raising=False)
    assert client.post('/api/auth/wechat', json={'code': 'unused'}).status_code == 503
    monkeypatch.setattr(wechat, 'exchange', lambda body: ('customer-app', digest(body.code)))
    assert client.post('/api/auth/wechat', json={'code': 'new-customer'}).status_code == 400
    r = client.post('/api/auth/wechat', json={'code': 'new-customer', 'agreement': True})
    assert r.status_code == 200 and r.json()['user']['role'] == 'customer'
    assert 'openid' not in str(r.json()) and 'session_key' not in str(r.json())


def test_login_throttling_and_shorter_admin_session(client, headers):
    for _ in range(5):
        assert client.post('/api/auth/login', json={'username': 'user2', 'password': 'wrong'}).status_code == 401
    assert client.post('/api/auth/login', json={'username': 'user2', 'password': 'test-password'}).status_code == 429
    with SessionLocal() as db:
        token = headers[1]['Authorization'].split()[1]
        assert timedelta(hours=7) < db.get(LoginSession, digest(token)).expires_at - now() <= timedelta(hours=8)


def test_cumulative_after_sales_does_not_exceed_ordered_quantity(client, headers):
    with SessionLocal() as db:
        o = Order(number='TEST-V2', customer_id=2, service_id=1, idempotency_key='test-v2-order', request_hash='x', status='completed', total=100)
        db.add(o); db.flush()
        line = OrderLine(order_id=o.id, sku_id=1, quantity=3, unit_price=100, snapshot={}, shipped_quantity=3)
        db.add(line); db.flush(); oid, lid = o.id, line.id; db.commit()
    body = {'order_id': oid, 'line_id': lid, 'quantity': 2, 'category': 'damaged', 'description': '灯罩有破损'}
    assert client.post('/api/tickets', headers=headers[2], json=body).status_code == 201
    assert client.post('/api/tickets', headers=headers[2], json=body).status_code == 409
    assert client.post('/api/tickets', headers=headers[2], json={**body, 'quantity': 1}).status_code == 201


def test_heuristic_cannot_masquerade_as_constraint_compliant():
    lines = [{'sku_id': 1, 'quantity': 1}, {'sku_id': 2, 'quantity': 1}]
    quotes = [{'id': i, 'sku_id': i, 'merchant_id': i, 'price': 100, 'available_quantity': 2, 'freight': 0} for i in (1, 2)]
    result = greedy(lines, quotes, max_suppliers=1, budget=100)
    assert result['status'] == 'CONSTRAINT_VIOLATION' and not result['feasible']
    assert set(result['violations']) == {'supplier_limit', 'budget'}


def test_additive_migration_preserves_legacy_rows(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'legacy.db'))
    with engine.begin() as c:
        c.execute(text('CREATE TABLE wishlist (id INTEGER PRIMARY KEY, note TEXT)'))
        c.execute(text("INSERT INTO wishlist VALUES (1, 'retain')"))
    upgrade(engine); upgrade(engine)
    with engine.connect() as c:
        assert tuple(c.execute(text('SELECT note, version FROM wishlist')).one()) == ('retain', 1)


def test_unpublished_media_is_not_visible_to_other_signed_in_users(client, headers):
    from test_business import upload
    draft = upload(client, headers[4], 'product')
    assert client.get('/api/media/' + draft, headers=headers[4]).status_code == 200
    assert client.get('/api/media/' + draft, headers=headers[2]).status_code == 404
    assert client.get('/api/media/' + draft, headers=headers[5]).status_code == 404
    assert client.get('/api/public-media/' + draft).status_code == 404
