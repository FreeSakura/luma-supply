import os
import tempfile
from pathlib import Path

TEST_ROOT = Path(tempfile.mkdtemp(prefix="luma-tests-"))
os.environ["DATA_DIR"] = str(TEST_ROOT)
os.environ["DATABASE_URL"] = "sqlite:///" + str(TEST_ROOT / "test.db")
os.environ["APP_ENV"] = "development"

import pytest
from fastapi.testclient import TestClient
from backend.db import Base, engine, SessionLocal
from backend.main import app
from backend.models import User, Merchant, Product, SKU, Quote, PricingRule, now
from backend.security import password_hash
from datetime import timedelta


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for i, role in enumerate(["admin", "customer", "customer", "merchant", "merchant", "staff"], 1):
            db.add(User(id=i, username=f"user{i}", name=f"User {i}", role=role, password_hash=password_hash("test-password"), permissions=["catalog"] if role == "staff" else []))
        db.flush()
        for i, uid in [(1,4),(2,5)]: db.add(Merchant(id=i,user_id=uid,shop_name=f"Shop {i}",status="approved"))
        p=Product(id=1,name="台灯",title="黑色台灯",category="台灯",owner_id=1);db.add(p);db.flush()
        db.add_all([SKU(id=1,product_id=1,code="L-1",initial_price=10000),SKU(id=2,product_id=1,code="L-2",initial_price=15000)])
        db.add(PricingRule(id=1,multiplier_bp=12000,created_by=1));db.flush()
        for qid,sid,mid,price,freight in [(1,1,1,5000,3000),(2,1,2,5500,200),(3,2,1,7000,3000),(4,2,2,7100,200)]:
            db.add(Quote(id=qid,sku_id=sid,merchant_id=mid,version=1,price=price,available_quantity=10,lead_days=2,freight=freight,valid_until=now()+timedelta(days=30),status="approved"))
        db.commit()
    with TestClient(app) as c: yield c


@pytest.fixture
def headers(client):
    result={}
    for i in range(1,7):
        r=client.post('/api/auth/login',json={'username':f'user{i}','password':'test-password'})
        assert r.status_code==200
        result[i]={'Authorization':'Bearer '+r.json()['token']}
    return result
