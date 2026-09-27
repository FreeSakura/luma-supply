from datetime import timedelta
from backend.db import SessionLocal
from backend.models import SKU, Product, Quote, Merchant, User, PricingRule, now


def test_constraints_apply_to_one_sku_and_counts_before_pagination(client):
    with SessionLocal() as db:
        db.get(SKU, 1).stock_status = 'unavailable'
        db.get(SKU, 1).attributes = {'cct_k': 3000}
        db.get(SKU, 2).attributes = {'cct_k': 4000}
        db.commit()
    assert client.get('/api/catalog/page?max_price=7000&available_only=true').json()['total'] == 0
    page = client.get('/api/catalog/page?max_price=8400&available_only=true&cct_k=4000').json()
    assert page['total'] == 1 and page['next_offset'] == 1 and not page['has_more']
    card = page['items'][0]
    assert card['selected_sku_id'] == 2 and card['min_price'] == 8400
    assert client.get('/api/catalog/page?q=L-1&cct_k=4000').json()['total'] == 0
    assert client.get('/api/catalog/page?max_price=0').json()['items'] == []
    assert client.get('/api/catalog/page?max_price=-1').status_code == 422
    assert client.get('/api/catalog/page?sort=unknown').status_code == 422


def test_price_sort_is_global_stable_and_preserves_eligible_variant(client):
    with SessionLocal() as db:
        for pid, price in [(2, 2000), (3, 1000), (4, 1000)]:
            db.add(Product(id=pid, name=f'灯具 {pid}', title='系列灯具', category='吊灯'))
            db.flush()
            db.add(SKU(product_id=pid, code=f'SORT-{pid}', initial_price=price))
        db.commit()
    pages = [client.get('/api/catalog/page', params={'sort': 'price_asc', 'limit': 2, 'offset': offset}).json() for offset in [0, 2]]
    cards = pages[0]['items'] + pages[1]['items']
    assert [p['id'] for p in cards] == [4, 3, 2, 1]
    assert [p['min_price'] for p in cards] == [1200, 1200, 2400, 6000]
    assert pages[0]['total'] == pages[1]['total'] == 4
    assert pages[0]['has_more'] and not pages[1]['has_more']
    assert [p['id'] for p in client.get('/api/catalog/products?sort=price_desc').json()] == [1, 2, 4, 3]
    for card in cards:
        sku = next(s for s in card['skus'] if s['id'] == card['selected_sku_id'])
        assert sku['price'] == card['min_price']


def test_catalog_price_matches_live_rules_and_excludes_invalid_offers(client):
    def first_price():
        card = client.get('/api/catalog/page').json()['items'][0]
        sku = next(s for s in card['skus'] if s['id'] == card['selected_sku_id'])
        assert card['min_price'] == sku['price']
        return card['min_price']
    assert first_price() == 6000
    with SessionLocal() as db:
        db.get(Merchant, 1).status = 'disabled'
        db.commit()
    assert first_price() == 6600
    with SessionLocal() as db:
        db.get(User, 5).active = False
        db.commit()
    assert first_price() == 12000
    with SessionLocal() as db:
        db.get(Merchant, 1).status = 'approved'
        db.get(Quote, 1).valid_until = now() - timedelta(days=1)
        db.get(Quote, 3).status = 'pending'
        db.get(SKU, 1).initial_price = 10001
        db.get(PricingRule, 1).multiplier_bp = 15000
        db.commit()
    assert first_price() == 15002  # half-up, not float/banker's rounding
    assert client.get('/api/catalog/page?max_price=15001').json()['total'] == 0
    with SessionLocal() as db:
        db.get(SKU, 2).manual_price = 9999
        db.commit()
    assert first_price() == 9999
