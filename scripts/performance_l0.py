"""Isolated L0 dataset and three measured rounds; never writes the business database."""
import argparse
import asyncio
import json
import os
import platform
import secrets
import subprocess
import sys
import threading
import time
from datetime import timedelta
from pathlib import Path
import httpx
import numpy as np

ROOT=Path(__file__).resolve().parents[1]


def prepare(folder):
    os.environ['DATA_DIR']=str(folder)
    os.environ['DATABASE_URL']='sqlite:///'+str(folder/'lumasupply.db')
    os.environ['APP_ENV']='development'
    from backend.db import Base,engine,SessionLocal
    from backend.models import User,Merchant,Product,SKU,Quote,PricingRule,Media,Order,OrderLine,Procurement,IndexTask,now
    from backend.security import password_hash
    from scripts.seed import draw_lamp,CATEGORIES,COLORS
    Base.metadata.create_all(engine)
    password=secrets.token_urlsafe(14)
    with SessionLocal() as db:
        if db.query(User).count():raise ValueError('Use a fresh load-test directory')
        for i in range(1,13):db.add(User(id=i,username=f'load{i}',name=f'Load {i}',role='admin' if i==1 else 'customer' if i==2 else 'merchant',password_hash=password_hash(password)))
        db.flush()
        for i in range(10):db.add(Merchant(id=i+1,user_id=i+3,shop_name=f'Supplier {i}',status='approved'))
        db.add(PricingRule(multiplier_bp=13000,created_by=1));db.flush()
        skus=[]
        for p in range(100):
            product=Product(name=f'灯具 {p}',title=f'暖金 {CATEGORIES[p%6]} 空间照明',category=CATEGORIES[p%6],owner_id=1);db.add(product);db.flush()
            for v in range(3):
                images=[]
                for image in range(4):
                    mid=f'load-{p}-{v}-{image}';path=folder/'media'/f'{mid}.png'
                    draw_lamp(p%6,COLORS[p%4][1],v,path,view=image%2)
                    db.add(Media(id=mid,owner_id=1,purpose='product',mime='image/png',path=str(path)));images.append(mid)
                sku=SKU(product_id=product.id,code=f'L0-{p:03}-{v}',initial_price=10000+p*100+v*500,attributes={'cct_k':3000+v*1000,'power_w':18+v*10},images=images)
                db.add(sku);db.flush();skus.append(sku.id)
                for supplier in range(1,11):db.add(Quote(merchant_id=supplier,sku_id=sku.id,version=1,price=8000+p*80+supplier*10,available_quantity=1000,freight=supplier*100,valid_until=now()+timedelta(days=30),status='approved'))
        for i in range(1000):
            order=Order(number=f'L0-{i:05}',customer_id=2,service_id=1,idempotency_key=f'l0-{i:05}',request_hash='fixture',total=30000)
            db.add(order);db.flush();db.add(Procurement(order_id=order.id))
            for j in range(3):db.add(OrderLine(order_id=order.id,sku_id=skus[(i*3+j)%300],quantity=1,unit_price=10000,snapshot={'code':f'FIXTURE-{j}'}))
        db.add(IndexTask(reason='L0 dataset'));db.commit()
    return password


async def benchmark(folder,password,port,samples,rounds):
    base=f'http://127.0.0.1:{port}'
    async with httpx.AsyncClient(base_url=base,timeout=30,limits=httpx.Limits(max_connections=12,max_keepalive_connections=12)) as client:
        for _ in range(100):
            try:
                if (await client.get('/api/health')).status_code==200:break
            except httpx.HTTPError:pass
            await asyncio.sleep(.2)
        auth=await client.post('/api/auth/login',json={'username':'load2','password':password});auth.raise_for_status()
        headers={'Authorization':'Bearer '+auth.json()['token']}
        for _ in range(200):
            if (folder/'index/current').exists():break
            await asyncio.sleep(.2)
        records=[]
        for round_id in range(1,rounds+1):
            for name,concurrency in [('catalog',8),('orders',8),('search',4)]:
                sem=asyncio.Semaphore(concurrency)
                async def one():
                    async with sem:
                        start=time.perf_counter()
                        try:
                            if name=='catalog':r=await client.get('/api/catalog/page?limit=24')
                            elif name=='orders':r=await client.get('/api/orders?limit=50',headers=headers)
                            else:r=await client.post('/api/search',headers=headers,json={'image_id':'load-0-0-0','text':'暖金吊灯','limit':10})
                            status=r.status_code
                        except httpx.HTTPError:status=0
                        return {'ms':(time.perf_counter()-start)*1000,'status':status}
                for _ in range(20):await one()
                start=time.perf_counter();raw=await asyncio.gather(*(one() for _ in range(samples)));seconds=time.perf_counter()-start
                lat=[x['ms'] for x in raw]
                row={'round':round_id,'name':name,'requests':samples,'concurrency':concurrency,'errors':sum(x['status']!=200 for x in raw),'p50_ms':float(np.percentile(lat,50)),'p95_ms':float(np.percentile(lat,95)),'p99_ms':float(np.percentile(lat,99)),'throughput_rps':samples/seconds,'raw':raw}
                records.append(row);print(json.dumps({k:v for k,v in row.items() if k!='raw'}),flush=True)
        return records


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path,default=ROOT/'local-only/performance-l0-v21');parser.add_argument('--port',type=int,default=8002);parser.add_argument('--samples',type=int,default=1000);parser.add_argument('--rounds',type=int,default=3);args=parser.parse_args()
    folder=args.directory.resolve();folder.mkdir(parents=True,exist_ok=True)
    password=prepare(folder)
    log=(folder/'server.log').open('w',encoding='utf-8')
    process=subprocess.Popen([sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port',str(args.port)],cwd=ROOT,env=os.environ.copy(),stdout=log,stderr=log,**({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}))
    resources=[];stop=threading.Event();affinity=[]
    try:
        import psutil
        parent=psutil.Process(process.pid)
        affinity=parent.cpu_affinity()[:4];parent.cpu_affinity(affinity)
        def sample():
            while not stop.wait(.5):
                try:
                    procs=[parent]+parent.children(recursive=True)
                    for p in procs:p.cpu_affinity(affinity)
                    resources.append({'rss_bytes':sum(p.memory_info().rss for p in procs),'cpu_seconds':sum(sum(p.cpu_times()[:2]) for p in procs)})
                except psutil.Error:pass
        thread=threading.Thread(target=sample,daemon=True);thread.start()
    except ImportError:pass
    try:
        records=asyncio.run(benchmark(folder,password,args.port,args.samples,args.rounds))
        result={'version':'2.1.0','environment':platform.platform(),'python':platform.python_version(),'server_cpu_affinity':affinity,'dataset':{'spus':100,'skus':300,'images':1200,'merchants':10,'quotes':3000,'orders':1000,'order_lines':3000},'warmup_per_case_per_round':20,'resources':{'peak_rss_bytes':max((r['rss_bytes'] for r in resources),default=None),'samples':resources},'results':records}
        (folder/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    finally:
        stop.set();process.terminate();process.wait(timeout=15);log.close()


if __name__=='__main__':main()
