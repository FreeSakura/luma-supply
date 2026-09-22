"""Small, bounded local latency check; intentionally not a large load-test suite."""
import asyncio
import json
import platform
from pathlib import Path
from time import perf_counter
import httpx
import numpy as np

ROOT=Path(__file__).resolve().parents[1]


async def run():
    password=json.loads((ROOT/'local-only/demo-accounts.json').read_text(encoding='utf-8'))['password']
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000',timeout=30) as client:
        token=(await client.post('/api/auth/login',json={'username':'customer','password':password})).json()['token']
        headers={'Authorization':'Bearer '+token}
        results=[]
        for name,count,concurrency in [('catalog',80,8),('search',30,4)]:
            semaphore=asyncio.Semaphore(concurrency)
            async def one():
                async with semaphore:
                    start=perf_counter()
                    r=await client.get('/api/catalog/products') if name=='catalog' else await client.post('/api/search',headers=headers,json={'image_id':'demo-0-0-0','text':'暖金吊灯','limit':10})
                    return {'ms':(perf_counter()-start)*1000,'status':r.status_code}
            await one()  # warm-up is excluded, and explicitly reported
            start=perf_counter();measurements=await asyncio.gather(*(one() for _ in range(count)));seconds=perf_counter()-start
            latencies=[x['ms'] for x in measurements]
            results.append({'name':name,'requests':count,'concurrency':concurrency,'errors':sum(x['status']!=200 for x in measurements),'p50_ms':float(np.percentile(latencies,50)),'p95_ms':float(np.percentile(latencies,95)),'throughput_rps':count/seconds,'raw':measurements})
        result={'environment':platform.platform(),'python':platform.python_version(),'base_url':'127.0.0.1:8000','dataset':{'spus':18,'skus':36,'index_images':72},'warmup_requests_per_case':1,'search_includes':'HTTP, stored-image decoding, feature extraction, retrieval, business filtering, log transaction; excludes initial image upload','results':results}
        output=ROOT/'local-only/experiments/performance.json';output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({**result,'results':[{k:v for k,v in r.items() if k!='raw'} for r in results]},ensure_ascii=False))


if __name__=='__main__':asyncio.run(run())
