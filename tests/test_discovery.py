from backend.db import SessionLocal
from backend.models import Product, SKU
from backend.catalog import search_products
from backend.search import build_index
from test_business import upload


def test_page_counts_match_visible_filtered_products(client):
    with SessionLocal() as db:
        for i, status in [(2, 'active'), (3, 'pending'), (4, 'active')]:
            db.add(Product(id=i, name=f'灯 {i}', title='灯', category='吊灯', status=status))
        db.flush()
        db.add(SKU(product_id=2, code='NEW', initial_price=1000))
        db.add(SKU(product_id=3, code='PENDING', initial_price=1000))
        db.add(SKU(product_id=4, code='HIDDEN', initial_price=1000, status='pending'))
        db.commit()
    page = client.get('/api/catalog/page', params={'limit': 1}).json()
    assert page['total'] == 2 and page['has_more'] and page['next_offset'] == 1
    assert page['items'][0]['id'] == 2
    final = client.get('/api/catalog/page', params={'limit': 1, 'offset': page['next_offset']}).json()
    assert not final['has_more'] and final['items'][0]['id'] == 1
    filtered = client.get('/api/catalog/page', params={'category': '吊灯'}).json()
    assert filtered['total'] == 1 and [p['id'] for p in filtered['items']] == [2]
    empty = client.get('/api/catalog/page', params={'q': 'does-not-exist'}).json()
    assert empty['total'] == 0 and not empty['has_more'] and empty['items'] == []
    assert client.get('/api/catalog/page?limit=201').status_code == 422


def test_ranked_cards_keep_spec_price_order_and_exclude_unapproved(client):
    with SessionLocal() as db:
        db.add(SKU(id=3, product_id=1, code='PENDING', initial_price=1, status='pending'))
        db.commit()
        cards = search_products(db, [2, 3, 1, 9999])
    assert [c['selected_sku_id'] for c in cards] == [2, 1]
    assert cards[0]['min_price'] == 8400 and cards[1]['min_price'] == 6000
    assert all('initial_price' not in s and 'manual_price' not in s for c in cards for s in c['skus'])
    assert all(3 not in [s['id'] for s in c['skus']] for c in cards)


def test_search_returns_cards_outside_initial_hundred_products(client, headers):
    image_id = upload(client, headers[1], 'product')
    with SessionLocal() as db:
        db.get(SKU, 2).images = [image_id]
        db.get(SKU, 2).code = 'ARCHIVE-LAMP'
        for i in range(2, 107):
            db.add(Product(id=i, name=f'新灯 {i}', title='新灯', category='台灯'))
            db.flush()
            db.add(SKU(product_id=i, code=f'NEW-{i}', initial_price=1000))
        db.commit()
        build_index(db)
    initial = client.get('/api/catalog/products').json()
    assert 1 not in [p['id'] for p in initial]
    response = client.post('/api/search', headers=headers[2], json={'text': 'ARCHIVE-LAMP'})
    assert response.status_code == 200, response.text
    result = response.json()
    assert [h['sku_id'] for h in result['results']] == [2]
    assert result['products'][0]['id'] == 1
    assert result['products'][0]['selected_sku_id'] == 2
    assert result['products'][0]['min_price'] == result['results'][0]['price']
