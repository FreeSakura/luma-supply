from io import BytesIO
from datetime import timedelta
from PIL import Image
from backend.db import SessionLocal
from backend.models import Quote, Order, now


def upload(client, headers, purpose='proof'):
    data=BytesIO();Image.new('RGB',(20,20),'white').save(data,format='PNG')
    r=client.post('/api/media',headers=headers,data={'purpose':purpose},files={'file':('proof.png',data.getvalue(),'image/png')})
    assert r.status_code==201,r.text
    return r.json()['id']


def order(client,h,quantity=2,key='order-key-123'):
    r=client.post('/api/orders',headers=h[1],json={'customer_id':2,'items':[{'sku_id':1,'quantity':quantity},{'sku_id':2,'quantity':1}],'idempotency_key':key})
    assert r.status_code==201,r.text
    return r.json()


def confirmed_plan(client,h,quantity=2):
    o=order(client,h,quantity)
    r=client.post(f"/api/orders/{o['id']}/confirm",headers=h[2],json={'version':o['version'],'delivery_mode':'pickup'})
    assert r.status_code==200,r.text
    p=client.post(f"/api/orders/{o['id']}/procurement/plan",headers=h[1],json={})
    assert p.status_code==200,p.text
    return o,p.json()


def test_complete_business_journey(client,headers):
    h=headers;o,p=confirmed_plan(client,h)
    assert p['plan']['status']=='OPTIMAL'
    assert p['plan']['total_cost'] < p['plan']['baselines']['unit_price']['total_cost']
    r=client.post(f"/api/orders/{o['id']}/procurement/confirm",headers=h[1],json={'version':p['version']});assert r.status_code==200,r.text
    proof=upload(client,h[1])
    r=client.post(f"/api/orders/{o['id']}/procurement/complete",headers=h[1],json={'media_ids':[proof]});assert r.status_code==200,r.text
    # Partial shipments must not allow premature receipt.
    for n,line in enumerate(o['lines']):
        body={'idempotency_key':f'shipment-{n}-123','items':[{'line_id':line['id'],'quantity':line['quantity']}],'proof_media_ids':[proof]}
        r=client.post(f"/api/orders/{o['id']}/shipments",headers=h[1],json=body);assert r.status_code==201,r.text
        again=client.post(f"/api/orders/{o['id']}/shipments",headers=h[1],json=body);assert again.json()['id']==r.json()['id']
        if n==0: assert client.post(f"/api/orders/{o['id']}/receive",headers=h[2],json={}).status_code==409
    assert client.get('/api/media/'+proof,headers=h[2]).status_code==200
    assert client.get('/api/public-media/'+proof).status_code==404
    assert client.post(f"/api/orders/{o['id']}/receive",headers=h[2],json={}).status_code==200
    assert client.post('/api/reviews',headers=h[2],json={'order_id':o['id'],'sku_id':1,'text':'收到完好'}).status_code==201
    ticket=client.post('/api/tickets',headers=h[2],json={'order_id':o['id'],'line_id':o['lines'][0]['id'],'quantity':1,'category':'missing','description':'缺少安装螺丝'})
    assert ticket.status_code==201
    for state in ['processing','resolved','closed']:
        assert client.patch('/api/tickets/'+str(ticket.json()['id']),headers=h[1],json={'status':state,'note':'记录处理过程'}).status_code==200


def test_roles_ownership_and_customer_cost_privacy(client,headers):
    h=headers;o=order(client,h)
    assert client.get(f"/api/orders/{o['id']}",headers=h[3]).status_code==403
    assert client.get('/api/quotes',headers=h[2]).status_code==403
    assert client.get('/api/orders',headers=h[6]).status_code==403
    assert client.get('/api/admin/catalog',headers=h[6]).status_code==200
    catalog=client.get('/api/catalog/products').json()
    assert 'initial_price' not in catalog[0]['skus'][0]
    detail=client.get(f"/api/orders/{o['id']}",headers=h[2]).json()
    assert 'procurement' not in detail
    assert 'unit_cost' not in str(detail)


def test_idempotency_and_price_snapshot(client,headers):
    h=headers;o=order(client,h)
    again=order(client,h);assert o['id']==again['id']
    clash=client.post('/api/orders',headers=h[1],json={'customer_id':2,'items':[{'sku_id':1,'quantity':9}],'idempotency_key':'order-key-123'})
    assert clash.status_code==409
    assert client.post('/api/admin/pricing',headers=h[1],json={'multiplier_bp':20000}).status_code==200
    assert client.get(f"/api/orders/{o['id']}",headers=h[2]).json()['total']==o['total']


def test_quote_version_expiry_and_disable(client,headers):
    h=headers
    old=client.get('/api/catalog/products').json()[0]['skus'][0]['price']
    payload={'sku_id':1,'price':2000,'available_quantity':20,'valid_until':(now()+timedelta(days=5)).isoformat()}
    q=client.post('/api/quotes',headers=h[4],json=payload).json()
    assert client.get('/api/catalog/products').json()[0]['skus'][0]['price']==old
    assert client.post(f"/api/quotes/{q['id']}/review",headers=h[1],json={'approve':True}).status_code==200
    assert client.get('/api/catalog/products').json()[0]['skus'][0]['price']==2400
    with SessionLocal() as db:
        db.get(Quote,q['id']).reserved_quantity=3;db.commit()
    revision=client.post('/api/quotes',headers=h[4],json={**payload,'price':2100,'available_quantity':2}).json()
    assert client.post(f"/api/quotes/{revision['id']}/review",headers=h[1],json={'approve':True}).status_code==400
    revision=client.post('/api/quotes',headers=h[4],json={**payload,'price':2100,'available_quantity':8}).json()
    approved=client.post(f"/api/quotes/{revision['id']}/review",headers=h[1],json={'approve':True})
    assert approved.status_code==200 and approved.json()['reserved_quantity']==3
    assert client.post('/api/admin/merchants/1/disable',headers=h[1],json={}).status_code==200
    assert client.get('/api/catalog/products').json()[0]['skus'][0]['price']==6600
    assert client.get('/api/quotes',headers=h[4]).status_code==401


def test_stale_procurement_and_stock_shortage(client,headers):
    h=headers;o,p=confirmed_plan(client,h)
    qid=p['plan']['allocation'][0]['quote_id']
    with SessionLocal() as db:
        db.get(Quote,qid).valid_until=now()-timedelta(seconds=1);db.commit()
    r=client.post(f"/api/orders/{o['id']}/procurement/confirm",headers=h[1],json={'version':p['version']})
    assert r.status_code==409
    with SessionLocal() as db: assert all(q.reserved_quantity==0 for q in db.query(Quote))


def test_unknown_stock_is_not_unlimited(client,headers):
    with SessionLocal() as db:
        db.query(Quote).filter_by(sku_id=1).update({'available_quantity':None});db.commit()
    o,p=confirmed_plan(client,headers)
    assert p['plan']['status']=='INFEASIBLE'
    assert p['status']=='exception'


def test_upload_boundary_and_external_configuration(client,headers):
    r=client.post('/api/media',headers=headers[2],data={'purpose':'query'},files={'file':('photo.jpg',b'<script>bad</script>','image/jpeg')})
    assert r.status_code==400
    proof=upload(client,headers[2],'query')
    assert client.get('/api/media/'+proof,headers=headers[3]).status_code==403
    r=client.post('/api/search',headers=headers[2],json={'image_id':proof,'provider':'aliyun'})
    assert r.status_code==503
    assert client.post('/api/auth/wechat',json={'code':'test'}).status_code==503


def test_optimistic_confirmation_and_settings_limits(client,headers):
    o=order(client,headers)
    assert client.post(f"/api/orders/{o['id']}/confirm",headers=headers[2],json={'version':99,'delivery_mode':'pickup'}).status_code==409
    assert client.put('/api/settings',headers=headers[1],json={'support':[],'customer_banners':[],'merchant_banners':[]}).status_code==422
