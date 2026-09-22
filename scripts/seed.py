"""Create local demo users and original procedural lamp illustrations, idempotently."""
import json
import os
import random
import secrets
from datetime import timedelta
from pathlib import Path
from PIL import Image, ImageDraw
from backend.db import Base, engine, SessionLocal, ROOT, RUNTIME
from backend.models import User, Merchant, Product, SKU, Quote, PricingRule, Media, Setting, Address, IndexTask, now
from backend.security import password_hash

CATEGORIES = ["吊灯", "台灯", "落地灯", "壁灯", "吸顶灯", "射灯"]
COLORS = [("暖金", "#b48e53"), ("墨黑", "#303633"), ("奶白", "#ddd7c7"), ("砖红", "#a5503d")]


def draw_lamp(kind, color, variant, path, view=0, scene=False, seed=0):
    rng = random.Random(seed)
    im = Image.new("RGB", (640, 480), "#f1efe8" if not scene else rng.choice(["#ddd6c8", "#ced8d8", "#c9c5b9"]))
    d = ImageDraw.Draw(im)
    if scene:
        d.rectangle((0, 350, 640, 480), fill="#a49580")
        d.rectangle((430, 60, 570, 280), fill="#edf0e9", outline="#827e70", width=8)
        d.line((500, 60, 500, 280), fill="#827e70", width=4)
        d.rounded_rectangle((25, 300, 180, 430), radius=12, fill="#8f9c92")
    x = 320 + view * 12
    stem = "#53554b"
    glow = "#fff5cf"
    width = 90 + variant * 9
    d.ellipse((170, 418, 470, 446), fill="#e2ded3" if not scene else "#8b806e")
    if kind == 0:
        d.line((x, 0, x, 120), fill=stem, width=5)
        d.polygon([(x-width, 130), (x+width,130), (x+width+40,270), (x-width-40,270)], fill=color)
        d.ellipse((x-width-40, 246, x+width+40, 291), fill=glow)
        d.ellipse((x-width, 116, x+width, 147), fill=color)
    elif kind in [1, 2]:
        top = 95 if kind == 2 else 145
        d.line((x, top+60, x, 412), fill=stem, width=9)
        d.ellipse((x-65,400,x+65,429),fill=color)
        d.polygon([(x-width+15,top),(x+width-15,top),(x+width+20,top+115),(x-width-20,top+115)],fill=color)
        d.ellipse((x-width-20,top+98,x+width+20,top+128),fill=glow)
        if variant % 2: d.line((x+width-5, top+117, x+width-5, top+165),fill=stem,width=3)
    elif kind == 3:
        d.rounded_rectangle((x-110,120,x-75,315),radius=10,fill=stem)
        d.line((x-70,250,x+20,250),fill=color,width=12)
        d.ellipse((x-20,130,x+140,290),fill=color)
        d.ellipse((x,150,x+120,270),fill=glow)
    elif kind == 4:
        d.ellipse((x-width-40,140,x+width+40,300),fill=color)
        d.ellipse((x-width-25,154,x+width+25,282),fill=glow)
        for k in range(variant % 3):
            d.ellipse((x-50+k*18,180+k*12,x+50-k*18,255-k*12),outline=color,width=3)
    else:
        d.rounded_rectangle((x-130,115,x+130,132),radius=5,fill=stem)
        for offset in [-80, 0, 80]:
            d.line((x+offset,125,x+offset,180),fill=stem,width=6)
            d.rounded_rectangle((x+offset-26,160,x+offset+26,235+variant*3),radius=12,fill=color)
            d.ellipse((x+offset-22,218+variant*3,x+offset+22,244+variant*3),fill=glow)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return [0.27, 0.0, 0.47, 0.9] if scene else None


def seed(password=None):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.query(User).count():
            print("Existing data retained. No reset performed."); return
        password = password or os.getenv("DEMO_PASSWORD") or secrets.token_urlsafe(12)
        users = []
        for username, role, name in [("admin", "admin", "平台管理员"), ("customer", "customer", "演示客户"), ("merchant", "merchant", "云栖灯饰"), ("merchant2", "merchant", "序光照明"), ("merchant3", "merchant", "拾光工坊")]:
            u = User(username=username, role=role, name=name, password_hash=password_hash(password)); db.add(u); db.flush(); users.append(u)
        merchants = []
        for i, u in enumerate(users[2:]):
            m = Merchant(user_id=u.id, shop_name=u.name, legal_name="演示负责人", phone=f"演示电话-{i+1}", address="演示供货地址", status="approved"); db.add(m); db.flush(); merchants.append(m)
        db.add(Address(user_id=users[1].id, recipient="演示收件人", phone="演示联系电话", detail="演示校区 教学楼 101"))
        db.add(PricingRule(multiplier_bp=13000, created_by=users[0].id))
        for i in range(18):
            kind = i % 6; cname, color = COLORS[(i // 6) % 4]
            product = Product(name=f"{['弧光','拾野','云屿'][i//6]} {CATEGORIES[kind]}", title=f"{cname} 简约 {CATEGORIES[kind]} 客厅卧室灯具", category=CATEGORIES[kind], description="原创程序绘制的灯具演示图。规格、供货与价格均为课程演示数据，不是实际销售承诺。", owner_id=users[0].id)
            db.add(product); db.flush()
            for s in range(2):
                media_ids = []
                for v in range(2):
                    mid = f"demo-{i}-{s}-{v}"
                    path = RUNTIME / "media" / f"{mid}.png"
                    draw_lamp(kind, color, i//6 + s*2, path, v)
                    db.add(Media(id=mid, owner_id=users[0].id, purpose="product", mime="image/png", path=str(path)))
                    media_ids.append(mid)
                sku = SKU(product_id=product.id, code=f"LM-{i+1:03d}-{s+1}", color=cname, size_mm=f"{300+s*150} × {300+s*150}", specification=f"{18+s*12}W / {3000+s*1000}K", attributes={"power_w": 18+s*12, "cct_k": 3000+s*1000, "voltage_v": 220, "material": "金属", "style": "简约"}, images=media_ids, initial_price=18000+i*2700+s*5000, stock_status="available")
                db.add(sku); db.flush()
                for j,m in enumerate(merchants):
                    price = int(sku.initial_price * (0.60 + (i+j*2)%5*0.05))
                    db.add(Quote(merchant_id=m.id, sku_id=sku.id, version=1, price=price, available_quantity=50+j*20, min_quantity=1, lead_days=2+j*2, freight=[2500, 1000, 500][j], valid_until=now()+timedelta(days=180), status="approved"))
        # Deliberately nonfunctional placeholder, visibly identified until an operator uploads a real QR.
        path = RUNTIME / "media" / "demo-support.png"
        im=Image.new('RGB',(400,400),'#e6e8dc'); d=ImageDraw.Draw(im)
        d.text((70,170),"DEMO - CONFIGURE WECHAT QR",fill='#39493d'); im.save(path)
        db.add(Media(id="demo-support", owner_id=users[0].id, purpose="support", mime="image/png", path=str(path)))
        db.add(Setting(key="support", value=[{"image":"demo-support","nickname":"演示客服 请配置真实二维码"}]))
        for role in ["customer", "merchant"]: db.add(Setting(key=f"{role}_banners", value=[{"image":"demo-0-0-0","title":"以光为线，找到适合的灯","link":"/product/1"}]))
        db.add(IndexTask(reason="initial demo catalog")); db.commit()
        local = ROOT / "local-only"; local.mkdir(exist_ok=True)
        (local / "demo-accounts.json").write_text(json.dumps({"password":password,"accounts":[{"username":u.username,"role":u.role} for u in users]},ensure_ascii=False,indent=2),encoding="utf-8")
        print("Demo created: 18 SPUs, 36 SKUs, 108 quotes. Credentials: local-only/demo-accounts.json")


if __name__ == "__main__": seed()
