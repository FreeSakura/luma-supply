import base64
import json
import struct
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO
from pathlib import Path
import pytest
from PIL import Image
from fastapi import HTTPException
from backend.db import SessionLocal
from backend.models import LoginSession, LoginAttempt, Verification, User, SKU, Media, now
from backend.security import digest
from backend.auth_controls import totp, consume, bucket_key


def test_totp_matches_rfc6238_vectors():
    secret=base64.b32encode(b'12345678901234567890').decode()
    for instant, expected in [(59,'94287082'),(1111111109,'07081804'),(1111111111,'14050471'),(1234567890,'89005924'),(2000000000,'69279037'),(20000000000,'65353130')]:
        assert totp(secret, instant//30, 8)==expected


def test_mfa_enforced_and_code_cannot_be_replayed(client, monkeypatch):
    from backend import auth_controls
    secret=base64.b32encode(b'12345678901234567890').decode()
    monkeypatch.setenv('MFA_TOTP_SECRETS',json.dumps({'1':secret}))
    monkeypatch.setattr(auth_controls.time,'time',lambda:1234567890)
    data={'username':'user1','password':'test-password'}
    assert client.post('/api/auth/login',json=data).status_code==401
    result=client.post('/api/auth/login',json={**data,'otp':totp(secret,1234567890//30)})
    assert result.status_code==200
    h={'Authorization':'Bearer '+result.json()['token']}
    assert client.get('/api/me',headers=h).status_code==200
    assert client.post('/api/auth/login',json={**data,'otp':totp(secret,1234567890//30)}).status_code==401


def test_production_admin_requires_mfa_configuration(client, monkeypatch):
    monkeypatch.setenv('APP_ENV','production');monkeypatch.delenv('MFA_TOTP_SECRETS',raising=False);monkeypatch.delenv('MFA_SECRETS_FILE',raising=False)
    result=client.post('/api/auth/login',json={'username':'user1','password':'test-password'})
    assert result.status_code==503 and result.json()['code']=='service_unavailable'


def test_idle_management_session_expires_and_sensitive_action_requires_reauth(client, headers):
    token=digest(headers[1]['Authorization'].split()[1])
    with SessionLocal() as db:
        db.get(LoginSession,token).authenticated_at=now()-timedelta(minutes=16);db.commit()
    denied=client.post('/api/admin/pricing',headers=headers[1],json={'multiplier_bp':13000})
    assert denied.status_code==403 and denied.json()['code']=='reauth_required'
    assert client.post('/api/auth/reauth',headers=headers[1],json={'password':'test-password'}).status_code==200
    assert client.post('/api/admin/pricing',headers=headers[1],json={'multiplier_bp':13000}).status_code==200
    with SessionLocal() as db:
        db.get(LoginSession,token).last_seen_at=now()-timedelta(minutes=31);db.commit()
    assert client.get('/api/me',headers=headers[1]).status_code==401


def test_login_source_and_alias_limits(client, headers, monkeypatch):
    with SessionLocal() as db:db.get(User,2).phone='13800000002';db.commit()
    for _ in range(5):
        assert client.post('/api/auth/login',json={'username':'2','password':'wrong'}).status_code==401
    assert client.post('/api/auth/login',json={'username':'user2','password':'test-password'}).status_code==200
    for username in ['user2','13800000002','user2','13800000002','user2']:
        assert client.post('/api/auth/login',json={'username':username,'password':'wrong'}).status_code==401
    assert client.post('/api/auth/login',json={'username':'13800000002','password':'test-password'}).status_code==429
    monkeypatch.setenv('AUTH_SOURCE_LIMIT','1')
    with SessionLocal() as db:db.query(LoginAttempt).delete();db.commit()
    assert client.post('/api/auth/login',json={'username':'user3','password':'test-password'}).status_code==200
    result=client.post('/api/auth/login',json={'username':'user4','password':'test-password'})
    assert result.status_code==429 and result.headers['retry-after']=='300'


def test_failure_counter_updates_are_atomic(client):
    def fail(_):
        with SessionLocal() as db:consume(db,'parallel','example',600);db.commit()
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(fail,range(12)))
    with SessionLocal() as db:assert db.get(LoginAttempt,bucket_key('parallel','example')).failures==12


def test_verification_code_is_consumed_once_under_concurrent_login(client):
    with SessionLocal() as db:
        db.get(User,2).phone='13800000002';db.add(Verification(phone='13800000002',code_hash=digest('123456'),expires_at=now()+timedelta(minutes=5)));db.commit()
    def login(_):return client.post('/api/auth/login-code',json={'phone':'13800000002','code':'123456'}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(login,range(2)))
    assert codes.count(200)==1 and all(x in (200,400,409) for x in codes)


def test_lowercase_bearer_logout_revokes_token(client, headers):
    h={'Authorization':headers[2]['Authorization'].replace('Bearer','bearer')}
    assert client.post('/api/auth/logout',headers=h).status_code==200
    assert client.get('/api/me',headers=headers[2]).status_code==401


def test_unpublished_product_image_cannot_be_used_as_search_input(client, headers):
    from test_business import upload
    mid=upload(client,headers[4],'product')
    assert client.post('/api/search',headers=headers[2],json={'image_id':mid}).status_code==403


def test_image_orientation_preserved_and_fake_mp4_rejected(client, headers):
    im=Image.new('RGB',(30,10),'blue');exif=Image.Exif();exif[274]=6
    content=BytesIO();im.save(content,format='JPEG',exif=exif)
    response=client.post('/api/media',headers=headers[2],data={'purpose':'query'},files={'file':('image.jpg',content.getvalue(),'image/jpeg')})
    image=client.get('/api/media/'+response.json()['id'],headers=headers[2]);assert Image.open(BytesIO(image.content)).size==(10,30)
    fake=struct.pack('>I4s',16,b'ftyp')+b'isom0000'
    response=client.post('/api/media',headers=headers[2],data={'purpose':'review'},files={'file':('fake.mp4',fake,'video/mp4')})
    assert response.status_code==400


def test_price_cache_does_not_load_unrelated_quotes(client):
    from backend.catalog import price_info
    with SessionLocal() as db:
        assert price_info(db,db.get(SKU,1))['price']==6000
        assert set(db.info['price_context'][0])=={1}
        assert price_info(db,db.get(SKU,2))['price']==8400


def test_corrupt_index_returns_recoverable_service_error(client, headers, tmp_path, monkeypatch):
    from backend import search
    monkeypatch.setattr(search,'INDEX_ROOT',tmp_path);monkeypatch.setattr(search,'_loaded_version',None)
    (tmp_path/'current').write_text('broken');(tmp_path/'broken.json').write_text('{bad')
    r=client.post('/api/search',headers=headers[2],json={'text':'台灯'})
    assert r.status_code==503 and r.json()['code']=='service_unavailable'
    assert client.get('/api/catalog/page').status_code==200


def test_process_lock_prevents_second_publisher(tmp_path):
    import subprocess,sys
    from backend.filelocks import try_lock
    path=tmp_path/'publisher.lock'
    with try_lock(path) as first:
        assert first
        code='from pathlib import Path; from backend.filelocks import try_lock\nwith try_lock(Path('+repr(str(path))+')) as locked: assert not locked'
        subprocess.run([sys.executable,'-c',code],check=True)
    with try_lock(path) as reopened:assert reopened


def test_restore_detects_interrupted_and_modified_backup_before_copy(tmp_path):
    from scripts.restore import restore
    src=tmp_path/'backup';src.mkdir();(src/'lumasupply.db').write_bytes(b'placeholder')
    (src/'.backup-in-progress').write_text('unfinished')
    with pytest.raises(ValueError,match='interrupted'):restore(src,tmp_path/'dest')
    (src/'.backup-in-progress').unlink()
    (src/'backup-manifest.json').write_text(json.dumps({'files':[{'path':'lumasupply.db','sha256':'wrong'}]}))
    with pytest.raises(ValueError,match='checksum'):restore(src,tmp_path/'dest')
    assert not (tmp_path/'dest').exists()


def test_structured_validation_error_has_request_id(client, headers):
    r=client.post('/api/wishlist',headers=headers[2],json={'sku_id':1,'quantity':0})
    assert r.status_code==422 and r.json()['code']=='validation_error'
    assert r.json()['request_id']==r.headers['x-request-id']


def test_merchant_cannot_append_specs_to_another_owners_product(client, headers):
    result=client.post('/api/catalog/products/1/skus',headers=headers[4],json={'code':'FOREIGN-SKU','initial_price':1000})
    assert result.status_code==403


def test_concurrent_ticket_transitions_preserve_history(client, headers, monkeypatch):
    from backend import operations
    from backend.models import Ticket, Order, OrderLine
    from threading import Barrier
    with SessionLocal() as db:
        o=Order(number='TICKET-2.1',customer_id=2,service_id=1,idempotency_key='ticket-2.1',request_hash='x',status='completed',total=100)
        db.add(o);db.flush();line=OrderLine(order_id=o.id,sku_id=1,quantity=1,unit_price=100,snapshot={});db.add(line);db.flush()
        t=Ticket(order_id=o.id,line_id=line.id,user_id=2,quantity=1,category='damaged',description='破损',history=[]);db.add(t);db.flush();tid=t.id;db.commit()
    barrier=Barrier(2);get_original=operations.get
    def sync_get(db,model,pk):
        obj=get_original(db,model,pk)
        if model is Ticket:barrier.wait(timeout=10)
        return obj
    monkeypatch.setattr(operations,'get',sync_get)
    def change(status):return client.patch(f'/api/tickets/{tid}',headers=headers[1],json={'status':status,'note':status}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(change,['processing','need_information']))
    assert sorted(results)==[200,409]
    with SessionLocal() as db:assert len(db.get(Ticket,tid).history)==1


def test_order_pagination_batches_relations_and_finds_older_orders(client, headers):
    from backend.models import Order, OrderLine, Procurement
    from backend.db import engine
    from sqlalchemy import event
    with SessionLocal() as db:
        for i in range(120):
            o=Order(number=f'PAGE-{i:03}',customer_id=2,service_id=1,idempotency_key=f'page-key-{i}',request_hash='x',total=100)
            db.add(o);db.flush();db.add(OrderLine(order_id=o.id,sku_id=1,quantity=1,unit_price=100,snapshot={}));db.add(Procurement(order_id=o.id))
        db.commit()
    statements=[]
    def count(conn,cursor,statement,parameters,context,many):
        if statement.lstrip().upper().startswith('SELECT') and 'index_tasks' not in statement:statements.append(statement)
    event.listen(engine,'before_cursor_execute',count)
    try:first=client.get('/api/orders?limit=50',headers=headers[2]).json()
    finally:event.remove(engine,'before_cursor_execute',count)
    second=client.get('/api/orders?limit=50&offset=50',headers=headers[2]).json()
    assert len(first)==len(second)==50 and not ({x['id'] for x in first}&{x['id'] for x in second})
    assert len(statements)<=7
    found=client.get('/api/orders?q=PAGE-000',headers=headers[2]).json()
    assert len(found)==1 and found[0]['number']=='PAGE-000'
