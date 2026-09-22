"""Deterministic controlled experiments. No result is presented as real-photo accuracy."""
import argparse
import csv
import hashlib
import json
import platform
import random
import statistics
from pathlib import Path
from time import perf_counter
import numpy as np
from PIL import Image
from scripts.seed import draw_lamp, CATEGORIES, COLORS
from algorithms.retrieval import features, rank, ResNetEncoder, ChineseClipEncoder
from algorithms.procurement import solve, greedy, exhaustive

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'local-only'/'experiments'


def dump(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')


def metrics(predictions):
    ranks=[next((i+1 for i,x in enumerate(p['ranking']) if x==p['relevant_sku']),None) for p in predictions]
    n=max(1,len(ranks))
    return {**{f'hit@{k}':sum(r is not None and r<=k for r in ranks)/n for k in [1,5,10]},'mrr':sum(1/r if r else 0 for r in ranks)/n,'ndcg@10_binary':sum(1/np.log2(r+1) if r and r<=10 else 0 for r in ranks)/n,'p50_ms':float(np.percentile([p['latency_ms'] for p in predictions],50)),'p95_ms':float(np.percentile([p['latency_ms'] for p in predictions],95)),'queries':len(ranks),'hard_constraint_violations':sum(p['violations'] for p in predictions)}


def retrieval(include_deep=True,include_clip=False):
    records=[];queries=[]
    # These are procedural identities, not independently photographed products.
    families=list(range(72));random.Random(20260922).shuffle(families)
    validation=set(families[:24]);test=set(families[24:])
    for family in range(72):
        kind=family%6;ci=(family//6)%4;variant=family//24;cname,color=COLORS[ci]
        split='validation' if family in validation else 'test'
        price=10000+family*321
        for v in range(2):
            path=OUT/'dataset'/'gallery'/f'{family}-{v}.png'
            draw_lamp(kind,color,variant,path,view=v)
            records.append({'sku_id':family+1,'family_id':family,'path':str(path),'price':price,'category':CATEGORIES[kind],'text':f'{cname} {CATEGORIES[kind]} 简约灯具','attributes':{'color':cname},'stock_status':'available','view':v})
        for scene in [False,True]:
            path=OUT/'dataset'/'queries'/f'{family}-{int(scene)}.png'
            crop=draw_lamp(kind,color,variant,path,view=-1,scene=scene,seed=family+900)
            queries.append({'family_id':family,'split':split,'path':str(path),'crop':crop,'scene':scene,'text':f'{cname}{CATEGORIES[kind]}','relevant_sku':family+1,'category':CATEGORIES[kind],'budget':price+2000})
    # Exact duplicates across generated families are detected, and matching labels
    # remain identity labels. Ambiguous identities are explicitly counted.
    hashes={}
    for r in records:
        h=hashlib.sha256(Path(r['path']).read_bytes()).hexdigest();r['sha256']=h
        hashes.setdefault(h,[]).append(r['sku_id'])
    dump(OUT/'dataset'/'manifest.json',{'source':'Original deterministic procedural drawings; NOT real catalog photos','license':'Project-owned synthetic fixtures; private course use','seed':20260922,'gallery':records,'queries':queries,'splits':{'validation':sorted(validation),'test':sorted(test)},'identical_gallery_groups':[v for v in hashes.values() if len(set(v))>1]})
    matrix=np.vstack([features(Image.open(r['path'])) for r in records])
    color_matrix=np.vstack([features(Image.open(r['path']),color_only=True) for r in records])
    methods=['color-single','shape-single','shape-multiview','crop-multiview','crop-text-fusion']
    vectors={'handcrafted':matrix,'color':color_matrix}
    encoders={}
    if include_deep:
        import torch
        torch.set_num_threads(2)
        encoders['resnet18']=ResNetEncoder()
        methods.append('resnet18-multiview')
    if include_clip:
        encoders['chinese-clip']=ChineseClipEncoder('ViT-B-16',str(ROOT/'data'/'models'))
        methods.append('chinese-clip-fusion')
    for name,enc in encoders.items(): vectors[name]=np.vstack([enc.encode_image(Image.open(r['path'])) for r in records])
    # Choose fusion weight using validation only, before evaluating the fixed test split.
    weight_scores={}
    for w in [0.3,0.5,0.7,0.9]:
        predictions=[]
        for q in queries:
            if q['split']!='validation':continue
            vec=features(Image.open(q['path']),q['crop'])
            results=rank(vec,matrix,records,text=q['text'],image_weight=w,text_weight=1-w,limit=72)
            ids=[x['sku_id'] for x in results];r=ids.index(q['relevant_sku'])+1
            predictions.append(1/r)
        weight_scores[str(w)]=statistics.mean(predictions)
    weight=float(max(weight_scores,key=weight_scores.get))
    raw=[];summary=[]
    for method in methods:
        print('Retrieval',method,flush=True)
        predictions=[]
        for q in queries:
            if q['split']!='test':continue
            start=perf_counter();image=Image.open(q['path']);crop=q['crop'] if method in ['crop-multiview','crop-text-fusion','chinese-clip-fusion'] else None
            if method.startswith('resnet18'): vec=encoders['resnet18'].encode_image(image);mat=vectors['resnet18']
            elif method.startswith('chinese-clip'):vec=encoders['chinese-clip'].encode_image(image,crop);mat=vectors['chinese-clip']
            elif method.startswith('color'):vec=features(image,color_only=True);mat=color_matrix
            else:vec=features(image,crop);mat=matrix
            text=q['text'] if 'fusion' in method else ''
            filters={'max_price':q['budget'],'category':q['category']} if 'fusion' in method else {}
            clip_text=encoders['chinese-clip'].encode_text(text) if method.startswith('chinese-clip') else None
            hits=rank(vec,mat,records,text=text,image_weight=weight,text_weight=1-weight,filters=filters,multi_view=not method.endswith('single'),limit=72,clip_text_vector=clip_text)
            record={'method':method,'query':q['path'],'family_id':q['family_id'],'scene':q['scene'],'relevant_sku':q['relevant_sku'],'ranking':[h['sku_id'] for h in hits],'scores':[h['score'] for h in hits],'latency_ms':(perf_counter()-start)*1000,'violations':sum(h['price']>q['budget'] or h['category']!=q['category'] for h in hits[:10]) if filters else 0,'constraints_applied':bool(filters)}
            predictions.append(record);raw.append(record)
        summary.append({'method':method,**metrics(predictions),'studio_hit1':metrics([p for p in predictions if not p['scene']])['hit@1'],'scene_hit1':metrics([p for p in predictions if p['scene']])['hit@1']})
    dump(OUT/'retrieval_predictions.json',raw)
    result={'scope':'Controlled procedural fixture retrieval, not real-scene generalization; no training performed','gallery_images':len(records),'validation_queries':48,'test_queries':96,'selected_image_weight':weight,'validation_weight_mrr':weight_scores,'methods':summary,'limitations':['Gallery and queries are generated from common procedural families, so this is a functional/stress benchmark, not independent-photograph accuracy.','Several geometrically equivalent families may be visually ambiguous; the identity-based metrics penalize these cases.','No manually graded similar-product relevance; nDCG is binary identity relevance only.','Baseline methods do not apply hard constraints; zero violations for baselines is not a constraint metric.','Fusion combines explicit text and hard filters; its gain is not solely an encoder gain.'],'index_bytes':matrix.nbytes,'failure_cases':[p for p in raw if not p['ranking'] or p['ranking'][0]!=p['relevant_sku']][:12]}
    dump(OUT/'retrieval_results.json',result)
    with (OUT/'retrieval_metrics.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
    return result


def procurement():
    cases=[];measurements=[]
    for n,m in [(4,3),(10,5),(20,8),(40,12)]:
        for seed in range(10):
            rng=random.Random(1000+n*100+seed)
            lines=[{'sku_id':i,'quantity':rng.randint(1,15)} for i in range(n)]
            quotes=[{'id':i*m+j,'sku_id':i,'merchant_id':j,'price':rng.randint(1000,8000),'freight':500+j*500,'available_quantity':rng.randint(8,40),'min_quantity':1,'lead_days':rng.randint(1,10)} for i in range(n) for j in range(m)]
            # Ensure at least one feasible supplier per line, without prescribing the optimum.
            for i in range(n):quotes[i*m]['available_quantity']=40;quotes[i*m]['lead_days']=2
            config={'max_days':7,'time_limit':2}
            optimized=solve(lines,quotes,**config);baseline=greedy(lines,quotes,max_days=7);incremental=greedy(lines,quotes,prefer_fewer=True,max_days=7)
            oracle=exhaustive(lines,quotes,max_days=7) if n==4 else None
            if oracle:assert oracle['total_cost']==optimized['total_cost']
            row={'lines':n,'suppliers':m,'seed':seed,'status':optimized['status'],'optimized_cost':optimized['total_cost'],'unit_price_cost':baseline['total_cost'],'incremental_cost':incremental['total_cost'],'saving_percent':100*(baseline['total_cost']-optimized['total_cost'])/baseline['total_cost'],'elapsed_ms':optimized['elapsed_ms'],'used_suppliers':optimized['supplier_count'],'best_bound':optimized['best_bound'],'oracle_agrees':None if oracle is None else True}
            measurements.append(row);cases.append({'lines':lines,'quotes':quotes,'config':config,'result':optimized,'baseline':baseline,'incremental':incremental})
    dump(OUT/'procurement_instances.json',cases)
    summary=[]
    for n in [4,10,20,40]:
        rows=[r for r in measurements if r['lines']==n]
        summary.append({'lines':n,'runs':len(rows),'mean_saving_percent':statistics.mean(r['saving_percent'] for r in rows),'mean_latency_ms':statistics.mean(r['elapsed_ms'] for r in rows),'p95_latency_ms':float(np.percentile([r['elapsed_ms'] for r in rows],95)),'optimal_runs':sum(r['status']=='OPTIMAL' for r in rows)})
    result={'scope':'Synthetic supplier instances with known input constraints','raw':measurements,'summary':summary,'small_enumeration_instances':10,'oracle_agreements':sum(r['oracle_agrees'] is True for r in measurements)}
    dump(OUT/'procurement_results.json',result)
    with (OUT/'procurement_metrics.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(measurements[0]));w.writeheader();w.writerows(measurements)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--no-deep',action='store_true');parser.add_argument('--chinese-clip',action='store_true');args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    dump(OUT/'environment.json',{'platform':platform.platform(),'python':platform.python_version(),'numpy':np.__version__,'cpu':platform.processor(),'seed':20260922})
    retrieval(not args.no_deep,args.chinese_clip);procurement();print('Saved results to',OUT)
