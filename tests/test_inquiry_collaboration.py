from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from backend.db import SessionLocal
from backend.models import Inquiry, InquiryEvent, Order, OrderLine, Procurement
from test_inquiry_planning import wish


def inquiry(client, headers):
    existing = client.get('/api/wishlist', headers=headers[2]).json()
    wid = existing[0]['id'] if existing else wish(client, headers[2], quantity=2)
    result = client.post('/api/inquiries', headers=headers[2], json={'submission_key': uuid4().hex, 
        'wishlist_ids': [wid], 'message': '客厅灯具询价', 'requirements': {'project_name': '客厅改造'}
    })
    assert result.status_code == 201
    return result.json()


def order_payload(i, key):
    return {'customer_id': 2, 'items': [{'sku_id': 1, 'quantity': 2}],
            'inquiry_id': i['id'], 'idempotency_key': key}


def test_customer_service_conversation_keeps_snapshot_and_enforces_ownership(client, headers):
    i = inquiry(client, headers)
    base = f"/api/inquiries/{i['id']}"
    before = client.get(base, headers=headers[2]).json()
    for actor, message in [(2, ' 请确认开孔尺寸 '), (1, '需要您补充安装位置照片')]:
        r = client.post(base + '/messages', headers=headers[actor], json={'message': message})
        assert r.status_code == 201, r.text
    detail = client.get(base, headers=headers[2]).json()
    assert [e['action'] for e in detail['history']] == ['submitted', 'customer_message', 'service_reply']
    assert detail['history'][1]['message'] == '请确认开孔尺寸'
    assert detail['items'] == before['items'] and detail['estimate'] == before['estimate']
    assert any('客服回复' in n['message'] for n in client.get('/api/notifications', headers=headers[2]).json())
    for actor in [3, 4, 6]:
        assert client.get(base, headers=headers[actor]).status_code == 403
        assert client.post(base + '/messages', headers=headers[actor], json={'message': '无权补充'}).status_code == 403
    assert client.post(base + '/messages', headers=headers[2], json={'message': '   '}).status_code == 422


def test_withdrawn_or_closed_inquiry_cannot_receive_messages_or_create_orders(client, headers):
    for action, actor, expected in [('withdraw', 2, 'withdrawn'), ('close', 1, 'closed')]:
        i = inquiry(client, headers)
        base = f"/api/inquiries/{i['id']}"
        result = client.post(base + '/' + action, headers=headers[actor], json={'message': '本次需求不再继续'})
        assert result.status_code == 200 and result.json()['status'] == expected
        assert result.json()['history'][-1]['action'] == expected
        assert client.post(base + '/' + action, headers=headers[actor], json={'message': '重复操作'}).status_code == 409
        assert client.post(base + '/messages', headers=headers[1], json={'message': '不能继续'}).status_code == 409
        r = client.post('/api/orders', headers=headers[1], json=order_payload(i, f'closed-order-{i["id"]}'))
        assert r.status_code == 409
        filtered = client.get('/api/inquiries', headers=headers[2], params={'status': expected}).json()
        assert [row['id'] for row in filtered] == [i['id']]
    with SessionLocal() as db:
        assert db.query(Order).count() == db.query(OrderLine).count() == db.query(Procurement).count() == 0


def test_role_specific_actions_and_legacy_timeline(client, headers):
    i = inquiry(client, headers)
    base = f"/api/inquiries/{i['id']}"
    assert client.post(base+'/withdraw', headers=headers[1], json={'message':'不是客户'}).status_code == 403
    assert client.post(base+'/close', headers=headers[2], json={'message':'不是客服'}).status_code == 403
    with SessionLocal() as db:
        legacy = Inquiry(user_id=2, items=[{'sku_id':1,'quantity':1}], message='历史询价')
        db.add(legacy); db.commit(); legacy_id=legacy.id
    detail = client.get(f'/api/inquiries/{legacy_id}', headers=headers[2]).json()
    assert detail['history'] == [] and detail['estimate'] is None
    r = client.post(f'/api/inquiries/{legacy_id}/messages', headers=headers[2], json={'message':'补充旧需求'})
    assert r.status_code == 201 and len(r.json()['history']) == 1


def test_concurrent_conversion_creates_exactly_one_order(client, headers):
    i = inquiry(client, headers)
    barrier = Barrier(2)
    def convert(key):
        barrier.wait(timeout=10)
        return client.post('/api/orders', headers=headers[1], json=order_payload(i, key))
    with ThreadPoolExecutor(max_workers=2) as pool:
        requests = [pool.submit(convert, key) for key in ['parallel-inquiry-a', 'parallel-inquiry-b']]
        results = [r.result(timeout=30) for r in requests]
    assert sorted(r.status_code for r in results) == [201, 409], [r.text for r in results]
    winner = next(r.json() for r in results if r.status_code == 201)
    with SessionLocal() as db:
        assert db.query(Order).count() == db.query(OrderLine).count() == db.query(Procurement).count() == 1
        assert db.get(Inquiry, i['id']).order_id == winner['id']
        assert db.query(InquiryEvent).filter_by(inquiry_id=i['id'], action='ordered').count() == 1
    detail = client.get(f"/api/inquiries/{i['id']}", headers=headers[2]).json()
    assert detail['status'] == 'ordered' and winner['number'] in detail['history'][-1]['message']
    assert client.post(f"/api/inquiries/{i['id']}/withdraw", headers=headers[2], json={'message':'来迟了'}).status_code == 409


def test_commit_failure_is_reported_before_a_success_response(client, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app
    from backend import security
    credentials = {'username': 'user2', 'password': 'test-password'}
    first = client.post('/api/auth/login', json=credentials)
    token = first.json()['token']
    # A colliding session primary key fails on commit, after the handler has returned.
    monkeypatch.setattr(security.secrets, 'token_urlsafe', lambda size: token)
    with TestClient(app, raise_server_exceptions=False) as failing_client:
        failed = failing_client.post('/api/auth/login', json=credentials)
    assert failed.status_code == 409, failed.text
    assert 'token' not in failed.json()
    assert client.get('/api/me', headers={'Authorization': 'Bearer ' + token}).status_code == 200
