import random
import numpy as np
from PIL import Image
from algorithms.procurement import solve, exhaustive, greedy
from algorithms.retrieval import features, rank


def test_solver_matches_independent_enumeration():
    for seed in range(12):
        rng=random.Random(seed)
        lines=[{'sku_id':i,'quantity':rng.randint(1,4)} for i in range(4)]
        quotes=[{'id':i*3+j,'sku_id':i,'merchant_id':j,'price':rng.randint(10,150),'freight':rng.randint(0,70),'available_quantity':10,'lead_days':rng.randint(1,4)} for i in range(4) for j in range(3)]
        result=solve(lines,quotes,max_suppliers=2)
        oracle=exhaustive(lines,quotes,max_suppliers=2)
        assert result['status']=='OPTIMAL'
        assert result['total_cost']==oracle['total_cost']


def test_fusion_normalization_multiview_and_hard_constraints():
    entries=[{'sku_id':1,'price':100,'category':'lamp','text':'黑色 台灯','attributes':{},'stock_status':'available'}, {'sku_id':1,'price':100,'category':'lamp','text':'黑色 台灯','attributes':{},'stock_status':'available'}, {'sku_id':2,'price':200,'category':'lamp','text':'红色 壁灯','attributes':{},'stock_status':'available'}]
    vectors=np.asarray([[0,1],[1,0],[.9,.1]])
    result=rank(np.asarray([1,0]),vectors,entries,filters={'max_price':100})
    assert len(result)==1 and result[0]['sku_id']==1 and result[0]['score']==1
    text=rank(None,vectors,entries,text='红色壁灯')
    assert text[0]['sku_id']==2


def test_image_feature_contract_and_invalid_crop():
    import pytest
    f=features(Image.new('RGB',(100,100),'red'))
    assert np.isfinite(f).all() and abs(np.linalg.norm(f)-1)<1e-5
    with pytest.raises(ValueError): features(Image.new('RGB',(10,10)),[.9,.9,.5,.5])


def test_greedy_charges_increased_freight_for_an_existing_supplier():
    lines = [{'sku_id': 1, 'quantity': 1}, {'sku_id': 2, 'quantity': 1}]
    offers = [
        {'id': 1, 'sku_id': 1, 'merchant_id': 1, 'price': 10, 'freight': 10, 'available_quantity': 1},
        {'id': 2, 'sku_id': 2, 'merchant_id': 1, 'price': 10, 'freight': 100, 'available_quantity': 1},
        {'id': 3, 'sku_id': 2, 'merchant_id': 2, 'price': 20, 'freight': 10, 'available_quantity': 1},
    ]
    result = greedy(lines, offers, prefer_fewer=True)
    assert [a['quote_id'] for a in result['allocation']] == [1, 3]
    assert result['total_cost'] == 50 == exhaustive(lines, offers)['total_cost']
