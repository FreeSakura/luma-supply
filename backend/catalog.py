from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session
from .db import session
from .models import Product, SKU, ProductChange, Quote, Merchant, User, PricingRule, IndexTask, Wishlist, now
from .security import current_user, require, audit, notify, notify_staff
from .common import get, expect, view
from .accounts import DecisionIn

router = APIRouter(prefix="/api")


def valid_quotes(db, sku_id=None):
    query = db.query(Quote).join(Merchant).join(User, Merchant.user_id == User.id).filter(Quote.status == "approved", Quote.active.is_(True), Quote.deleted.is_(False), Quote.valid_until > now(), Merchant.status == "approved", User.active.is_(True))
    if sku_id is not None: query = query.filter(Quote.sku_id == sku_id)
    return query


def price_info(db, sku):
    if "price_context" not in db.info:
        groups = {}
        for quote in valid_quotes(db): groups.setdefault(quote.sku_id, []).append(quote)
        db.info["price_context"] = (groups, db.query(PricingRule).order_by(PricingRule.id.desc()).first())
    groups, rule = db.info["price_context"]
    quotes = groups.get(sku.id, [])
    base = min([sku.initial_price] + [q.price for q in quotes])
    multiplier = rule.multiplier_bp if rule else 10000
    amount = sku.manual_price if sku.manual_price is not None else (base * multiplier + 5000) // 10000
    return {"price": amount, "pricing_rule_id": rule.id if rule else None, "quote_count": len({q.merchant_id for q in quotes}), "stock_status": sku.stock_status}


def sku_view(db, sku, internal=False):
    result = view(sku, exclude=() if internal else ("initial_price", "manual_price"))
    result.update(price_info(db, sku))
    return result


def product_view(db, product, internal=False, selected_sku=None):
    if "catalog_skus" not in db.info:
        db.info["catalog_skus"] = {}
    groups_by_product = db.info["catalog_skus"]
    if product.id not in groups_by_product:
        groups_by_product[product.id] = db.query(SKU).filter_by(product_id=product.id).all()
    skus = [s for s in groups_by_product[product.id] if internal or s.status == "active"]
    rows = [sku_view(db, s, internal) for s in skus]
    if not rows: return None
    prices = [s["price"] for s in rows]
    groups = db.info["price_context"][0]
    return {**view(product), "skus": rows, "min_price": min(prices), "max_price": max(prices), "selected_sku_id": selected_sku or min(rows, key=lambda s: s["price"])["id"], "quote_count": len({q.merchant_id for s in rows for q in groups.get(s["id"], [])})}


@router.get("/catalog/categories")
def categories(db: Session = Depends(session)):
    return [x[0] for x in db.query(Product.category).filter_by(status="active").distinct().order_by(Product.category)]


@router.get("/catalog/products")
def products(q: str = "", category: str = "", limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(session)):
    q = q.strip()
    active_skus = db.query(SKU.id).filter(SKU.product_id == Product.id, SKU.status == "active")
    rows = db.query(Product).filter(Product.status == "active", active_skus.exists())
    if category: rows = rows.filter_by(category=category)
    if q:
        # SQL LIKE wildcards must remain literal user input (e.g. SKU "LED_1").
        term = q.lower()
        matching_skus = active_skus.filter(
            func.lower(SKU.code).contains(term, autoescape=True)
            | func.lower(SKU.color).contains(term, autoescape=True)
            | func.lower(SKU.specification).contains(term, autoescape=True)
        )
        rows = rows.filter(func.lower(Product.name).contains(term, autoescape=True)
                           | func.lower(Product.title).contains(term, autoescape=True)
                           | matching_skus.exists())
    page = rows.order_by(Product.id.desc()).offset(offset).limit(limit).all()
    page_skus = {p.id: [] for p in page}
    if page:
        for sku in db.query(SKU).filter(SKU.product_id.in_(page_skus), SKU.status == "active"):
            page_skus[sku.product_id].append(sku)
    db.info["catalog_skus"] = page_skus
    results = []
    for product in page:
        result = product_view(db, product)
        if not result: continue
        matched = [s for s in result["skus"] if any(q.lower() in s[field].lower() for field in ("code", "color", "specification"))]
        if matched and q:
            selected = min(matched, key=lambda s: s["price"])
            result["selected_sku_id"], result["min_price"] = selected["id"], selected["price"]
        results.append(result)
    return results


@router.get("/catalog/products/{product_id}")
def product_detail(product_id: int, sku: int | None = None, db: Session = Depends(session)):
    obj = get(db, Product, product_id); expect(obj.status == "active", "商品未上架", 404)
    result = product_view(db, obj, selected_sku=sku)
    expect(result, "商品无可售规格", 404)
    if sku: expect(sku in [x["id"] for x in result["skus"]], "规格不属于该商品")
    return result


class SKUIn(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    color: str = Field(default="", max_length=40)
    size_mm: str = Field(default="", max_length=80)
    specification: str = Field(default="", max_length=150)
    unit: str = Field(default="个", max_length=20)
    attributes: dict = Field(default_factory=dict)
    images: list[str] = Field(default_factory=list, max_length=9)
    initial_price: int = Field(ge=0, le=100000000)
    stock_status: Literal["available", "unavailable", "unconfirmed"] = "available"


class ProductIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    title: str = Field(min_length=2, max_length=200)
    category: str = Field(min_length=1, max_length=50)
    description: str = Field(default="", max_length=10000)
    custom: bool = False
    skus: list[SKUIn] = Field(min_length=1, max_length=50)


def check_images(db, user, skus):
    from .media import owned_media
    for sku in skus:
        owned_media(db, user, sku.images, purposes=["product"])


def merchant_for(db, user):
    merchant = db.query(Merchant).filter_by(user_id=user.id).first()
    expect(merchant and merchant.status == "approved", "请先完成商家认证", 403)
    return merchant


def queue_index(db, reason):
    db.add(IndexTask(reason=reason))


@router.post("/catalog/products", status_code=201)
def create_product(body: ProductIn, user=Depends(require("admin", "staff", "merchant", module="catalog")), db: Session = Depends(session)):
    if user.role == "merchant": merchant_for(db, user)
    expect(len({s.code for s in body.skus}) == len(body.skus), "SKU 编码重复")
    expect(not db.query(SKU).filter(SKU.code.in_([s.code for s in body.skus])).first(), "SKU 编码已存在", 409)
    check_images(db, user, body.skus)
    obj = Product(**body.model_dump(exclude={"skus"}), owner_id=user.id, status="pending" if user.role == "merchant" else "active")
    db.add(obj); db.flush()
    for s in body.skus: db.add(SKU(product_id=obj.id, **s.model_dump(), status=obj.status))
    db.flush()
    if obj.status == "pending": notify_staff(db, "catalog", f"商品待审核：{obj.name}", "catalog")
    else: queue_index(db, f"product:{obj.id}")
    audit(db, user, "product.create", obj.id)
    return product_view(db, obj, internal=True)


class ProductEdit(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    title: str = Field(min_length=2, max_length=200)
    category: str = Field(min_length=1, max_length=50)
    description: str = Field(max_length=10000)
    custom: bool = False


@router.patch("/catalog/products/{product_id}")
def edit_product(product_id: int, body: ProductEdit, user=Depends(require("admin", "staff", "merchant", module="catalog")), db: Session = Depends(session)):
    obj = get(db, Product, product_id)
    if user.role == "merchant":
        merchant_for(db, user); expect(obj.owner_id == user.id, "只能编辑自己提交的商品", 403)
        change = ProductChange(product_id=obj.id, user_id=user.id, payload=body.model_dump())
        db.add(change); db.flush(); notify_staff(db, "catalog", f"商品资料修改待审：{obj.name}", "catalog")
        return {"change_id": change.id, "status": "pending"}
    for k, v in body.model_dump().items(): setattr(obj, k, v)
    audit(db, user, "product.edit", obj.id); queue_index(db, f"product:{obj.id}")
    return product_view(db, obj, internal=True)


@router.post("/catalog/products/{product_id}/skus", status_code=201)
def create_sku(product_id: int, body: SKUIn, user=Depends(require("admin", "staff", "merchant", module="catalog")), db: Session = Depends(session)):
    obj = get(db, Product, product_id)
    if user.role == "merchant": merchant_for(db, user)
    expect(not db.query(SKU).filter_by(code=body.code).first(), "SKU 编码已存在", 409)
    check_images(db, user, [body])
    status = "pending" if user.role == "merchant" else "active"
    sku = SKU(product_id=obj.id, **body.model_dump(), status=status); db.add(sku); db.flush()
    if status == "pending": notify_staff(db, "catalog", f"SKU 待审核：{sku.code}", "catalog")
    else: queue_index(db, f"sku:{sku.id}")
    return sku_view(db, sku, True)


@router.get("/admin/catalog")
def admin_catalog(user=Depends(require("admin", "staff", "merchant", module="catalog")), db: Session = Depends(session)):
    rows = db.query(Product)
    if user.role == "merchant": rows = rows.filter_by(owner_id=user.id)
    return [product_view(db, x, True) for x in rows]


@router.get("/admin/catalog/changes")
def changes(user=Depends(require("admin", "staff", module="catalog")), db: Session = Depends(session)):
    return [{**view(x), "before": view(get(db, Product, x.product_id))} for x in db.query(ProductChange).order_by(ProductChange.id.desc())]


@router.post("/admin/catalog/changes/{change_id}/review")
def review_change(change_id: int, body: DecisionIn, user=Depends(require("admin", "staff", module="catalog")), db: Session = Depends(session)):
    obj = get(db, ProductChange, change_id); expect(obj.status == "pending", "已处理", 409)
    expect(body.approve or body.reason.strip(), "驳回需要填写原因")
    obj.status = "approved" if body.approve else "rejected"; obj.reason = body.reason
    if body.approve:
        product = get(db, Product, obj.product_id)
        for k, v in obj.payload.items(): setattr(product, k, v)
        queue_index(db, f"change:{obj.id}")
    notify(db, obj.user_id, f"商品修改{obj.status}：{body.reason}", "catalog")
    audit(db, user, "product.review_change", obj.id, body.model_dump())
    return view(obj)


class CatalogState(BaseModel):
    status: Literal["active", "inactive", "deleted", "rejected"]
    reason: str = ""


@router.post("/admin/catalog/{product_id}/state")
def product_state(product_id: int, body: CatalogState, user=Depends(require("admin", "staff", module="catalog")), db: Session = Depends(session)):
    obj = get(db, Product, product_id); obj.status = body.status
    if body.status == "active":
        db.query(SKU).filter_by(product_id=obj.id, status="pending").update({"status": "active"})
    if obj.owner_id: notify(db, obj.owner_id, f"商品 {obj.name}：{body.status} {body.reason}", "catalog")
    queue_index(db, f"state:{obj.id}"); audit(db, user, "product.state", obj.id, body.model_dump())
    return view(obj)


@router.post("/admin/skus/{sku_id}/state")
def sku_state(sku_id: int, body: CatalogState, user=Depends(require("admin", "staff", module="catalog")), db: Session = Depends(session)):
    obj = get(db, SKU, sku_id); obj.status = body.status
    queue_index(db, f"sku:{sku_id}"); audit(db, user, "sku.state", sku_id, body.model_dump())
    return sku_view(db, obj, True)


class QuoteIn(BaseModel):
    sku_id: int
    price: int = Field(gt=0, le=100000000)
    available_quantity: int | None = Field(default=None, ge=0, le=1000000)
    min_quantity: int = Field(default=1, ge=1, le=1000000)
    lead_days: int = Field(default=3, ge=0, le=365)
    freight: int = Field(default=0, ge=0, le=10000000)
    valid_until: datetime


def submit_quote(db, user, body):
    merchant = merchant_for(db, user)
    sku = get(db, SKU, body.sku_id); expect(sku.status == "active", "只能报价已审核 SKU")
    expect(body.valid_until.replace(tzinfo=None) > now(), "有效期必须晚于当前时间")
    latest = db.query(func.max(Quote.version)).filter_by(merchant_id=merchant.id, sku_id=sku.id).scalar() or 0
    obj = Quote(merchant_id=merchant.id, version=latest + 1, **body.model_dump())
    obj.valid_until = body.valid_until.replace(tzinfo=None)
    db.add(obj); db.flush(); notify_staff(db, "quotes", f"新报价：{merchant.shop_name} / {sku.code}", "quotes")
    audit(db, user, "quote.submit", obj.id)
    return obj


@router.post("/quotes", status_code=201)
def quote_submit(body: QuoteIn, user=Depends(require("merchant")), db: Session = Depends(session)):
    return view(submit_quote(db, user, body))


@router.get("/quotes")
def quotes(user=Depends(require("admin", "staff", "merchant", module="quotes")), db: Session = Depends(session)):
    query = db.query(Quote)
    if user.role == "merchant": query = query.filter_by(merchant_id=db.query(Merchant).filter_by(user_id=user.id).one().id)
    return [{**view(q), "sku_code": get(db, SKU, q.sku_id).code, "shop_name": get(db, Merchant, q.merchant_id).shop_name} for q in query.order_by(Quote.id.desc())]


@router.post("/quotes/{quote_id}/review")
def quote_review(quote_id: int, body: DecisionIn, user=Depends(require("admin", "staff", module="quotes")), db: Session = Depends(session)):
    obj = get(db, Quote, quote_id)
    expect(obj.status == "pending" and not obj.deleted, "报价已处理", 409)
    expect(body.approve or body.reason.strip(), "驳回需要填写原因")
    if body.approve:
        expect(obj.valid_until > now(), "报价已过期")
        expect(get(db, Merchant, obj.merchant_id).status == "approved", "商家未通过认证")
        newer = db.query(Quote).filter(Quote.merchant_id == obj.merchant_id, Quote.sku_id == obj.sku_id, Quote.status == "approved", Quote.version > obj.version).first()
        expect(not newer, "已有更新批准版本", 409)
        previous = db.query(Quote).filter(Quote.merchant_id == obj.merchant_id, Quote.sku_id == obj.sku_id, Quote.status == "approved").order_by(Quote.version.desc()).first()
        if previous:
            obj.reserved_quantity = previous.reserved_quantity
            expect(obj.available_quantity is None or obj.available_quantity >= obj.reserved_quantity, "新报价供货总量小于已确认采购数量")
        db.query(Quote).filter(Quote.merchant_id == obj.merchant_id, Quote.sku_id == obj.sku_id, Quote.status == "approved").update({"active": False})
        obj.active = True
    obj.status = "approved" if body.approve else "rejected"; obj.reason = body.reason
    db.flush()
    notify(db, get(db, Merchant, obj.merchant_id).user_id, f"报价{obj.status}：{body.reason}", "quotes")
    if body.approve:
        for watch in db.query(Wishlist).filter_by(sku_id=obj.sku_id):
            if watch.watch_price or watch.watch_stock: notify(db, watch.user_id, f"关注的 {get(db, SKU, obj.sku_id).code} 报价/供货信息更新", "wishlist")
    audit(db, user, "quote.review", obj.id, body.model_dump())
    return view(obj)


class QuoteAction(BaseModel):
    action: Literal["withdraw", "resubmit", "delete"]


@router.post("/quotes/{quote_id}/action")
def quote_action(quote_id: int, body: QuoteAction, user=Depends(require("merchant")), db: Session = Depends(session)):
    obj = get(db, Quote, quote_id); merchant = merchant_for(db, user)
    expect(obj.merchant_id == merchant.id, "无权操作其他商家报价", 403)
    if body.action == "resubmit":
        return view(submit_quote(db, user, QuoteIn(**{k: getattr(obj, k) for k in QuoteIn.model_fields})))
    obj.active = False
    if body.action == "delete": obj.deleted = True
    audit(db, user, "quote." + body.action, obj.id)
    return view(obj)


class BatchQuotes(BaseModel):
    rows: list[QuoteIn] = Field(min_length=1, max_length=100)
    commit: bool = False


@router.post("/quotes/import")
def import_quotes(body: BatchQuotes, user=Depends(require("merchant")), db: Session = Depends(session)):
    merchant_for(db, user)
    errors = []
    seen = set()
    for i, row in enumerate(body.rows):
        sku = db.get(SKU, row.sku_id)
        if not sku or sku.status != "active": errors.append({"row": i + 1, "message": "SKU 不存在或未审核"})
        if row.sku_id in seen: errors.append({"row": i + 1, "message": "导入 SKU 重复"})
        seen.add(row.sku_id)
        if row.valid_until.replace(tzinfo=None) <= now(): errors.append({"row": i + 1, "message": "报价已过期"})
    if errors or not body.commit: return {"valid": not errors, "errors": errors, "rows": len(body.rows), "committed": False}
    return {"valid": True, "committed": True, "ids": [submit_quote(db, user, r).id for r in body.rows]}


class PricingIn(BaseModel):
    multiplier_bp: int = Field(ge=1000, le=100000)


def preview_pricing(db, multiplier):
    result = []
    for sku in db.query(SKU).filter_by(status="active"):
        base = min([sku.initial_price] + [q.price for q in valid_quotes(db, sku.id)])
        result.append({"sku_id": sku.id, "code": sku.code, "old": price_info(db, sku)["price"], "new": sku.manual_price if sku.manual_price is not None else (base * multiplier + 5000) // 10000})
    return result


@router.post("/admin/pricing/preview")
def price_preview(body: PricingIn, user=Depends(require("admin", "staff", module="catalog")), db: Session = Depends(session)):
    return preview_pricing(db, body.multiplier_bp)


@router.post("/admin/pricing")
def pricing(body: PricingIn, user=Depends(require("admin", "staff", module="catalog")), db: Session = Depends(session)):
    rule = PricingRule(**body.model_dump(), created_by=user.id); db.add(rule); db.flush()
    audit(db, user, "pricing.create", rule.id, body.model_dump())
    return view(rule)


class SKUPriceIn(BaseModel):
    manual_price: int | None = Field(default=None, ge=0, le=100000000)
    stock_status: Literal["available", "unavailable", "unconfirmed"]


@router.patch("/admin/skus/{sku_id}/price")
def sku_price(sku_id: int, body: SKUPriceIn, user=Depends(require("admin", "staff", module="catalog")), db: Session = Depends(session)):
    sku = get(db, SKU, sku_id)
    sku.manual_price, sku.stock_status = body.manual_price, body.stock_status
    audit(db, user, "sku.price", sku.id, body.model_dump())
    return sku_view(db, sku, True)
