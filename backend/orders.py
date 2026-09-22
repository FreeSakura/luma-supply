from datetime import timedelta
import json
import secrets
from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.orm import Session
from .db import session
from .models import Order, OrderLine, User, SKU, Product, Procurement, Shipment, Quote, Merchant, Address, Inquiry, now
from .security import current_user, require, audit, notify, digest
from .common import get, expect, view
from .catalog import sku_view, valid_quotes
from .media import owned_media
from algorithms.procurement import solve, greedy

router = APIRouter(prefix="/api")


@router.get("/order-customers")
def order_customers(user=Depends(require("admin", "staff", module="orders")), db: Session = Depends(session)):
    return [{"id": u.id, "username": u.username, "name": u.name} for u in db.query(User).filter_by(role="customer", active=True)]


def accessible_order(db, user, order_id, module="orders"):
    obj = get(db, Order, order_id)
    allowed = user.role == "admin" or user.role == "staff" and module in user.permissions or user.role == "customer" and obj.customer_id == user.id
    expect(allowed, "无权访问此订单", 403)
    return obj


def order_view(db, obj, detail=False, internal=False):
    result = view(obj, exclude=("idempotency_key", "request_hash", "address_snapshot"))
    result["customer_name"] = get(db, User, obj.customer_id).name
    result["service_name"] = get(db, User, obj.service_id).name
    result["lines"] = [view(x) for x in db.query(OrderLine).filter_by(order_id=obj.id)]
    procurement = db.query(Procurement).filter_by(order_id=obj.id).one()
    result["procurement_status"] = procurement.status
    result["shipment_status"] = "shipped" if all(x["shipped_quantity"] == x["quantity"] for x in result["lines"]) else "partial" if any(x["shipped_quantity"] for x in result["lines"]) else "unshipped"
    if detail:
        result["address_snapshot"] = obj.address_snapshot
        result["shipments"] = [view(x, exclude=("idempotency_key",)) for x in db.query(Shipment).filter_by(order_id=obj.id)]
    if internal: result["procurement"] = view(procurement)
    return result


class OrderItem(BaseModel):
    sku_id: int
    quantity: int = Field(ge=1, le=100000)
    unit_price: int | None = Field(default=None, ge=0, le=100000000)


class OrderIn(BaseModel):
    customer_id: int
    items: list[OrderItem] = Field(min_length=1, max_length=50)
    remark: str = Field(default="", max_length=3000)
    idempotency_key: str = Field(min_length=8, max_length=100)
    inquiry_id: int | None = None


@router.post("/orders", status_code=201)
def create_order(body: OrderIn, user=Depends(require("admin", "staff", module="orders")), db: Session = Depends(session)):
    signature = digest(json.dumps(body.model_dump(), sort_keys=True))
    old = db.query(Order).filter_by(idempotency_key=body.idempotency_key).first()
    if old:
        expect(old.request_hash == signature, "幂等键已用于其他请求", 409)
        return order_view(db, old)
    customer = get(db, User, body.customer_id); expect(customer.role == "customer" and customer.active, "请选择有效客户")
    expect(len({x.sku_id for x in body.items}) == len(body.items), "同一 SKU 请合并数量")
    obj = Order(number="LS" + now().strftime("%Y%m%d%H%M%S") + secrets.token_hex(3).upper(), customer_id=body.customer_id, service_id=user.id, idempotency_key=body.idempotency_key, request_hash=signature, remark=body.remark, total=0)
    db.add(obj); db.flush()
    for item in body.items:
        sku = get(db, SKU, item.sku_id); product = get(db, Product, sku.product_id)
        expect(sku.status == "active" and product.status == "active", "订单含未上架商品")
        snapshot = sku_view(db, sku)
        snapshot.update({"product_name": product.name, "category": product.category})
        price = item.unit_price if item.unit_price is not None else snapshot["price"]
        db.add(OrderLine(order_id=obj.id, sku_id=sku.id, quantity=item.quantity, unit_price=price, snapshot=snapshot))
        obj.total += price * item.quantity
    db.add(Procurement(order_id=obj.id)); db.flush()
    if body.inquiry_id:
        inquiry = get(db, Inquiry, body.inquiry_id)
        expect(inquiry.user_id == customer.id and inquiry.status == "open", "询价单不可转换", 409)
        inquiry.status, inquiry.order_id = "ordered", obj.id
    notify(db, customer.id, f"订单 {obj.number} 请确认收货信息", "orders")
    audit(db, user, "order.create", obj.id, {"total": obj.total})
    return order_view(db, obj)


@router.get("/orders")
def orders(q: str = "", user=Depends(current_user), db: Session = Depends(session)):
    rows = db.query(Order)
    if user.role == "customer": rows = rows.filter_by(customer_id=user.id)
    else: expect(user.role == "admin" or user.role == "staff" and "orders" in user.permissions, "无订单权限", 403)
    if q:
        rows = rows.join(User, User.id == Order.customer_id).filter((Order.number.contains(q)) | (User.name.contains(q)) | (User.username.contains(q)))
    return [order_view(db, x) for x in rows.order_by(Order.id.desc())]


@router.get("/orders/{order_id}")
def detail(order_id: int, user=Depends(current_user), db: Session = Depends(session)):
    obj = accessible_order(db, user, order_id)
    if user.role in ["admin", "staff"]: audit(db, user, "order.address_read", obj.id)
    return order_view(db, obj, detail=True)


class ConfirmIn(BaseModel):
    version: int
    delivery_mode: Literal["delivery", "pickup"]
    address_id: int | None = None


@router.post("/orders/{order_id}/confirm")
def confirm(order_id: int, body: ConfirmIn, user=Depends(require("customer")), db: Session = Depends(session)):
    obj = accessible_order(db, user, order_id)
    expect(obj.status == "awaiting_confirmation", "订单当前不可确认", 409)
    snapshot = None
    if body.delivery_mode == "delivery":
        address = get(db, Address, body.address_id)
        expect(address.user_id == user.id, "收货地址不属于当前客户", 403)
        snapshot = view(address, exclude=("user_id",))
    result = db.execute(update(Order).where(Order.id == obj.id, Order.version == body.version, Order.status == "awaiting_confirmation").values(status="confirmed", version=Order.version + 1, delivery_mode=body.delivery_mode, address_snapshot=snapshot))
    expect(result.rowcount == 1, "订单版本已变化，请刷新", 409)
    audit(db, user, "order.confirm", obj.id); db.flush(); db.refresh(obj)
    return order_view(db, obj)


class VersionIn(BaseModel):
    version: int


@router.post("/orders/{order_id}/cancel")
def cancel(order_id: int, body: VersionIn, user=Depends(current_user), db: Session = Depends(session)):
    obj = accessible_order(db, user, order_id)
    p = db.query(Procurement).filter_by(order_id=obj.id).one()
    expect(obj.status in ["awaiting_confirmation", "confirmed"] and p.status in ["draft", "planned", "exception"], "采购执行后请走售后流程", 409)
    result = db.execute(update(Order).where(Order.id == obj.id, Order.version == body.version, Order.status.in_(["awaiting_confirmation", "confirmed"])).values(status="cancelled", version=Order.version + 1))
    expect(result.rowcount == 1, "订单已变化", 409)
    p.status = "cancelled"; audit(db, user, "order.cancel", obj.id)
    return {"cancelled": True}


class PlanIn(BaseModel):
    max_days: int = Field(default=30, ge=0, le=365)
    max_suppliers: int | None = Field(default=None, ge=1, le=100)
    budget: int | None = Field(default=None, ge=0, le=10000000000)
    time_limit: float = Field(default=3, gt=0, le=10)


@router.get("/procurements")
def procurements(user=Depends(require("admin", "staff", module="procurement")), db: Session = Depends(session)):
    return [{**view(p), "order_number": get(db, Order, p.order_id).number} for p in db.query(Procurement).order_by(Procurement.id.desc())]


def procurement_inputs(db, obj):
    lines = [{"sku_id": x.sku_id, "quantity": x.quantity} for x in db.query(OrderLine).filter_by(order_id=obj.id)]
    quotes = []
    for q in valid_quotes(db).filter(Quote.sku_id.in_([x["sku_id"] for x in lines])):
        sku = get(db, SKU, q.sku_id)
        if sku.stock_status == "unavailable" or sku.status != "active" or get(db, Product, sku.product_id).status != "active": continue
        row = view(q); row["available_quantity"] = None if q.available_quantity is None else max(0, q.available_quantity - q.reserved_quantity)
        quotes.append(row)
    return lines, quotes


@router.post("/orders/{order_id}/procurement/plan")
def plan(order_id: int, body: PlanIn, user=Depends(require("admin", "staff", module="procurement")), db: Session = Depends(session)):
    obj = get(db, Order, order_id)
    expect(obj.status == "confirmed", "请先让客户确认订单", 409)
    procurement = db.query(Procurement).filter_by(order_id=obj.id).one()
    expect(procurement.status in ["draft", "planned", "exception"], "采购已执行", 409)
    lines, quotes = procurement_inputs(db, obj)
    result = solve(lines, quotes, **body.model_dump())
    result["baselines"] = {"unit_price": greedy(lines, quotes, max_days=body.max_days), "incremental_freight": greedy(lines, quotes, prefer_fewer=True, max_days=body.max_days)}
    procurement.plan, procurement.constraints = result, body.model_dump()
    procurement.planned_at = now(); procurement.version += 1
    procurement.status = "planned" if result["status"] in ["OPTIMAL", "FEASIBLE"] else "exception"
    audit(db, user, "procurement.plan", procurement.id, {"solver_status": result["status"]})
    return view(procurement)


@router.post("/orders/{order_id}/procurement/confirm")
def confirm_plan(order_id: int, body: VersionIn, user=Depends(require("admin", "staff", module="procurement")), db: Session = Depends(session)):
    obj = get(db, Order, order_id); p = db.query(Procurement).filter_by(order_id=obj.id).one()
    expect(obj.status == "confirmed" and p.status == "planned" and p.version == body.version, "采购方案已变化或不可确认", 409)
    expect(p.planned_at > now() - timedelta(minutes=30), "方案超过 30 分钟，请重新计算", 409)
    _, eligible = procurement_inputs(db, obj); eligible_by_id = {x["id"]: x for x in eligible}
    for allocation in p.plan["allocation"]:
        q = eligible_by_id.get(allocation["quote_id"])
        expect(q and q["version"] == allocation["quote_version"] and q["price"] == allocation["unit_cost"], "报价过期、下架或已更新，请重新计算", 409)
        expect(q["available_quantity"] is not None and q["available_quantity"] >= allocation["quantity"] and q["lead_days"] <= p.constraints["max_days"], "库存或交期已变化", 409)
        result = db.execute(update(Quote).where(Quote.id == q["id"], Quote.active.is_(True), Quote.status == "approved", Quote.valid_until > now(), Quote.available_quantity - Quote.reserved_quantity >= allocation["quantity"]).values(reserved_quantity=Quote.reserved_quantity + allocation["quantity"]))
        expect(result.rowcount == 1, "库存不足，请重新计算", 409)
    claimed = db.execute(update(Procurement).where(Procurement.id == p.id, Procurement.version == body.version, Procurement.status == "planned").values(status="processing", version=Procurement.version + 1))
    expect(claimed.rowcount == 1, "方案已被确认", 409)
    advanced = db.execute(update(Order).where(Order.id == obj.id, Order.status == "confirmed").values(status="fulfilling", version=Order.version + 1))
    expect(advanced.rowcount == 1, "订单状态已变化", 409)
    audit(db, user, "procurement.confirm", p.id)
    db.flush(); db.refresh(p)
    return view(p)


class ProofIn(BaseModel):
    media_ids: list[str] = Field(min_length=1, max_length=9)


@router.post("/orders/{order_id}/procurement/complete")
def procurement_complete(order_id: int, body: ProofIn, user=Depends(require("admin", "staff", module="procurement")), db: Session = Depends(session)):
    p = db.query(Procurement).filter_by(order_id=order_id).first(); expect(p, "采购记录不存在", 404)
    expect(p.status == "processing", "当前采购不可完成", 409)
    owned_media(db, user, body.media_ids, ["proof"])
    p.status, p.proof_media_ids = "completed", body.media_ids
    audit(db, user, "procurement.complete", p.id)
    return view(p)


class ShipItem(BaseModel):
    line_id: int
    quantity: int = Field(gt=0, le=100000)


class ShipmentIn(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=100)
    tracking: str = Field(default="", max_length=100)
    carrier: str = Field(default="", max_length=80)
    items: list[ShipItem] = Field(min_length=1, max_length=50)
    proof_media_ids: list[str] = Field(min_length=1, max_length=9)


@router.post("/orders/{order_id}/shipments", status_code=201)
def ship(order_id: int, body: ShipmentIn, user=Depends(require("admin", "staff", module="orders")), db: Session = Depends(session)):
    obj = accessible_order(db, user, order_id)
    old = db.query(Shipment).filter_by(idempotency_key=body.idempotency_key).first()
    if old:
        expect(old.order_id == obj.id and old.items == [x.model_dump() for x in body.items] and old.tracking == body.tracking and old.carrier == body.carrier and old.proof_media_ids == body.proof_media_ids, "幂等键冲突", 409)
        return view(old)
    procurement = db.query(Procurement).filter_by(order_id=obj.id).one()
    expect(obj.status == "fulfilling" and procurement.status == "completed", "采购完成后才能发货", 409)
    expect(obj.delivery_mode == "pickup" or body.tracking.strip(), "配送必须填写快递单号")
    expect(len({x.line_id for x in body.items}) == len(body.items), "发货行重复")
    owned_media(db, user, body.proof_media_ids, ["proof"])
    for item in body.items:
        line = get(db, OrderLine, item.line_id); expect(line.order_id == obj.id, "发货行不属于该订单")
        result = db.execute(update(OrderLine).where(OrderLine.id == line.id, OrderLine.shipped_quantity + item.quantity <= OrderLine.quantity).values(shipped_quantity=OrderLine.shipped_quantity + item.quantity))
        expect(result.rowcount == 1, "发货数量超过待发数量", 409)
    shipment = Shipment(order_id=obj.id, **body.model_dump()); db.add(shipment); db.flush()
    notify(db, obj.customer_id, f"订单 {obj.number} 已发货 / 可自提", "orders")
    audit(db, user, "shipment.create", shipment.id)
    return view(shipment)


@router.post("/orders/{order_id}/receive")
def receive(order_id: int, user=Depends(require("customer")), db: Session = Depends(session)):
    obj = accessible_order(db, user, order_id)
    expect(obj.status == "fulfilling", "当前订单不可签收", 409)
    lines = db.query(OrderLine).filter_by(order_id=obj.id).all()
    expect(all(x.shipped_quantity == x.quantity for x in lines), "订单尚有未发商品", 409)
    obj.status, obj.version = "completed", obj.version + 1
    db.query(Shipment).filter_by(order_id=obj.id).update({"received": True})
    audit(db, user, "order.receive", obj.id)
    return order_view(db, obj)
