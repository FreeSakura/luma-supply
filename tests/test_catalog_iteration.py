from sqlalchemy import event
from backend.db import SessionLocal, engine
from backend.models import Product, SKU
from backend.search import current_entries


def test_search_filters_before_pagination_and_keeps_matching_sku(client):
    with SessionLocal() as db:
        db.get(SKU, 2).code = "OLDER_100%"
        for i in range(2, 107):
            db.add(Product(id=i, name=f"新品 {i}", title="新品", category="台灯"))
            db.flush()
            db.add(SKU(product_id=i, code=f"NEW-{i}", initial_price=1000))
        db.commit()
    found = client.get('/api/catalog/products', params={'q': 'older_100%', 'limit': 1}).json()
    assert [p['id'] for p in found] == [1]
    assert found[0]['selected_sku_id'] == 2
    assert found[0]['min_price'] == next(s['price'] for s in found[0]['skus'] if s['id'] == 2)
    first = client.get('/api/catalog/products', params={'q': '新品', 'limit': 2}).json()
    second = client.get('/api/catalog/products', params={'q': '新品', 'limit': 2, 'offset': 2}).json()
    assert [p['id'] for p in first + second] == [106, 105, 104, 103]
    assert client.get('/api/catalog/products', params={'offset': -1}).status_code == 422


def test_literal_wildcards_and_unpublished_skus_do_not_match(client):
    with SessionLocal() as db:
        db.get(SKU, 2).code = "hidden%spec"
        db.get(SKU, 2).status = "pending"
        db.commit()
    assert client.get('/api/catalog/products', params={'q': '%'}).json() == []
    assert client.get('/api/catalog/products', params={'q': '_'}).json() == []
    assert client.get('/api/catalog/products', params={'q': 'hidden'}).json() == []


def test_index_metadata_refresh_preserves_vector_positions_and_batches_reads(client):
    with SessionLocal() as db:
        p = db.get(Product, 1)
        p.title = '新标题 warm-white'
        s = db.get(SKU, 1)
        s.images = ['retained']
        s.specification = '4000K'
        db.commit()
    indexed = [dict(sku_id=1, image_id='removed', text='旧标题'),
               dict(sku_id=1, image_id='retained', text='旧标题'),
               dict(sku_id=2, image_id='unpublished', text='旧标题')]
    statements = []
    def record(conn, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith('SELECT'): statements.append(statement)
    event.listen(engine, 'before_cursor_execute', record)
    try:
        with SessionLocal() as db:
            entries, positions = current_entries(db, indexed * 10)
    finally:
        event.remove(engine, 'before_cursor_execute', record)
    assert positions == list(range(1, 30, 3))
    assert len(entries) == 10
    assert all('warm-white' in e['text'] and '4000K' in e['text'] and '旧标题' not in e['text'] for e in entries)
    assert len(statements) == 3  # SKU/SPU join, valid offers, pricing rule; independent of view count.
