from uuid import uuid4
from backend.db import SessionLocal
from backend.models import Product, Wishlist


def create_wish(client, headers, **values):
    response = client.post('/api/wishlist', headers=headers, json={'sku_id': 1, 'room': '客厅', 'quantity': 2, **values})
    assert response.status_code == 200
    return response.json()['id']


def test_edit_moves_same_item_and_preserves_submitted_inquiry(client, headers):
    wid = create_wish(client, headers[2], watch_price=True)
    old = client.post('/api/inquiries', headers=headers[2], json={'submission_key': uuid4().hex, 'wishlist_ids': [wid]}).json()
    changed = client.patch(f'/api/wishlist/{wid}', headers=headers[2], json={'version': 1, 'room': '  书房  ', 'quantity': 4, 'note': '靠窗阅读区', 'watch_stock': True})
    assert changed.status_code == 200
    row = changed.json()
    assert (row['id'], row['sku_id'], row['room'], row['quantity']) == (wid, 1, '书房', 4)
    assert row['watch_price'] and row['watch_stock']  # omitted fields are preserved
    assert row['sku']['price'] == 6000 and row['product_name'] == '台灯'
    preview = client.post('/api/inquiries/preview', headers=headers[2], json={'wishlist_ids': [wid]}).json()
    assert preview['estimate']['goods_amount'] == 24000
    assert preview['items'][0]['note'] == '靠窗阅读区'
    saved = client.get(f"/api/inquiries/{old['id']}", headers=headers[2]).json()
    assert saved['items'][0]['room'] == '客厅' and saved['items'][0]['quantity'] == 2
    assert saved['estimate']['goods_amount'] == 12000
    assert len(client.get('/api/wishlist', headers=headers[2]).json()) == 1


def test_edit_checks_owner_and_room_conflict_without_losing_either_item(client, headers):
    first = create_wish(client, headers[2])
    second = create_wish(client, headers[2], room='卧室', quantity=3)
    assert client.patch(f'/api/wishlist/{first}', headers=headers[3], json={'version': 1, 'quantity': 8}).status_code == 403
    assert client.patch(f'/api/wishlist/{first}', headers=headers[4], json={'version': 1, 'quantity': 8}).status_code == 403
    response = client.patch(f'/api/wishlist/{first}', headers=headers[2], json={'version': 1, 'room': ' 卧室 ', 'quantity': 9})
    assert response.status_code == 409
    with SessionLocal() as db:
        assert db.get(Wishlist, first).quantity == 2 and db.get(Wishlist, first).room == '客厅'
        assert db.get(Wishlist, second).quantity == 3
        assert db.query(Wishlist).count() == 2


def test_invalid_edits_do_not_change_saved_values_and_unlisted_items_remain_manageable(client, headers):
    wid = create_wish(client, headers[2])
    for body in [{'room': '  '}, {'quantity': 0}, {'quantity': 1.5}, {'note': 'x' * 301}]:
        assert client.patch(f'/api/wishlist/{wid}', headers=headers[2], json={'version': 1, **body}).status_code == 422
    with SessionLocal() as db:
        assert db.get(Wishlist, wid).quantity == 2
        db.get(Product, 1).status = 'inactive'
        db.commit()
    assert client.patch(f'/api/wishlist/{wid}', headers=headers[2], json={'version': 1, 'note': '等待客服替代方案'}).status_code == 200
    preview = client.post('/api/inquiries/preview', headers=headers[2], json={'wishlist_ids': [wid]}).json()
    assert not preview['can_submit']
