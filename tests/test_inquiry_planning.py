from uuid import uuid4
from datetime import timedelta
from backend.db import SessionLocal
from backend.models import SKU, Product, Inquiry, InquiryBrief, now


def wish(client, headers, sku=1, room='客厅', quantity=1):
    r = client.post('/api/wishlist', headers=headers, json={'sku_id': sku, 'room': room, 'quantity': quantity})
    assert r.status_code == 200, r.text
    return r.json()['id']


def test_cct_filter_selects_matching_variant_not_cheapest(client):
    with SessionLocal() as db:
        db.get(SKU, 1).attributes = {'cct_k': 3000}
        db.get(SKU, 2).attributes = {'cct_k': 4000}
        db.add(SKU(id=3, product_id=1, code='PENDING', initial_price=1, attributes={'cct_k': 6500}, status='pending'))
        db.commit()
    assert client.get('/api/catalog/lighting-options').json()['cct_k'] == [3000, 4000]
    page = client.get('/api/catalog/page', params={'cct_k': 4000}).json()
    assert page['total'] == 1 and page['items'][0]['selected_sku_id'] == 2
    assert page['items'][0]['min_price'] == 8400
    assert client.get('/api/catalog/page?cct_k=6500').json()['total'] == 0
    # SKU keyword and temperature must apply to the same SKU, not separate variants.
    assert client.get('/api/catalog/page?q=L-1&cct_k=4000').json()['total'] == 0


def test_preview_groups_selected_rooms_and_does_not_write(client, headers):
    living = wish(client, headers[2], quantity=2)
    bedroom = wish(client, headers[2], sku=2, room='卧室', quantity=3)
    body = {'wishlist_ids': [living, living, bedroom], 'requirements': {'budget': 30000}}
    result = client.post('/api/inquiries/preview', headers=headers[2], json=body).json()
    assert result['estimate']['goods_amount'] == 37200
    assert result['estimate']['quantity'] == 5
    assert [r['amount'] for r in result['estimate']['rooms']] == [12000, 25200]
    assert result['estimate']['over_budget'] and result['estimate']['budget_gap'] == 7200
    assert result['can_submit']  # Asking for a quote above target budget is allowed.
    with SessionLocal() as db: assert db.query(Inquiry).count() == 0
    selected = client.post('/api/inquiries/preview', headers=headers[2], json={'wishlist_ids': [bedroom]}).json()
    assert selected['estimate']['quantity'] == 3 and len(selected['estimate']['rooms']) == 1


def test_inquiry_snapshot_and_structured_brief_survive_price_changes(client, headers):
    wid = wish(client, headers[2], quantity=2)
    tomorrow = (now() + timedelta(days=1)).date().isoformat()
    requirements = {'project_name': '客厅改造', 'budget': 10000, 'needed_by': tomorrow, 'destination': '上海', 'allow_alternatives': True}
    result = client.post('/api/inquiries', headers=headers[2], json={'submission_key': uuid4().hex, 'wishlist_ids': [wid], 'requirements': requirements})
    assert result.status_code == 201, result.text
    with SessionLocal() as db:
        db.get(SKU, 1).manual_price = 99999
        db.get(Product, 1).name = '修改后的名称'
        db.commit()
    saved = client.get('/api/inquiries', headers=headers[2]).json()[0]
    assert saved['requirements'] == requirements
    assert saved['estimate']['goods_amount'] == 12000
    assert saved['items'][0]['snapshot']['product_name'] == '台灯'
    assert saved['items'][0]['unit_price'] == 6000
    assert client.get('/api/inquiries', headers=headers[3]).json() == []
    assert client.get('/api/inquiries', headers=headers[4]).status_code == 403
    assert client.get('/api/inquiries', headers=headers[1]).json()[0]['requirements']['destination'] == '上海'
    with SessionLocal() as db:
        db.add(Inquiry(user_id=3, items=[{'sku_id': 1, 'quantity': 1, 'room': '旧清单', 'note': ''}], message='旧版本询价'))
        db.commit()
    legacy = client.get('/api/inquiries', headers=headers[3]).json()[0]
    assert legacy['requirements'] == {} and legacy['estimate'] is None


def test_inquiry_checks_ownership_and_revalidates_publication(client, headers):
    wid = wish(client, headers[2])
    assert client.post('/api/inquiries/preview', headers=headers[3], json={'wishlist_ids': [wid]}).status_code == 403
    with SessionLocal() as db:
        db.get(Product, 1).status = 'inactive'; db.commit()
    preview = client.post('/api/inquiries/preview', headers=headers[2], json={'wishlist_ids': [wid]}).json()
    assert not preview['can_submit']
    assert client.post('/api/inquiries', headers=headers[2], json={'submission_key': uuid4().hex, 'wishlist_ids': [wid]}).status_code == 409
    with SessionLocal() as db:
        assert db.query(Inquiry).count() == 0 and db.query(InquiryBrief).count() == 0
    yesterday = (now() - timedelta(days=1)).date().isoformat()
    assert client.post('/api/inquiries/preview', headers=headers[2], json={'wishlist_ids': [wid], 'requirements': {'needed_by': yesterday}}).status_code == 422
