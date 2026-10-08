from typing import Literal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import update, func
from .db import session
from .models import Wishlist, SKU, Product, Review, Ticket, OrderLine, Order, Notification, Setting, Audit, Procurement, Quote, IndexTask, SearchLog, now
from .security import current_user, require, audit, notify, notify_staff
from .common import get, expect, view
from .catalog import sku_view
from .orders import accessible_order
from .media import owned_media

router = APIRouter(prefix="/api")


class WishFields(BaseModel):
    room: str = Field(default="客厅", min_length=1, max_length=60)
    quantity: int = Field(default=1, ge=1, le=100000)
    note: str = Field(default="", max_length=300)
    watch_price: bool = False
    watch_stock: bool = False

    @field_validator('room', mode='before')
    @classmethod
    def trim_room(cls, value):
        return value.strip() if isinstance(value, str) else value


class WishIn(WishFields):
    sku_id: int


class WishEdit(WishFields):
    version: int = Field(ge=1)


def wish_view(db, wish):
    sku = get(db, SKU, wish.sku_id)
    return {**view(wish), "sku": sku_view(db, sku), "product_name": get(db, Product, sku.product_id).name}


@router.get("/wishlist")
def wishlist(user=Depends(require("customer")), db: Session = Depends(session, scope="function")):
    return [wish_view(db, w) for w in db.query(Wishlist).filter_by(user_id=user.id)]


@router.post("/wishlist")
def save_wish(body: WishIn, user=Depends(require("customer")), db: Session = Depends(session, scope="function")):
    sku = get(db, SKU, body.sku_id)
    expect(sku.status == "active" and get(db, Product, sku.product_id).status == "active", "商品未上架")
    obj = db.query(Wishlist).filter_by(user_id=user.id, sku_id=body.sku_id, room=body.room).first()
    if obj:
        expect(False, "此规格已在该房间，请打开清单编辑", 409)
    else: obj = Wishlist(user_id=user.id, **body.model_dump()); db.add(obj)
    db.flush(); return view(obj)


@router.patch("/wishlist/{wish_id}")
def edit_wish(wish_id: int, body: WishEdit, user=Depends(require("customer")), db: Session = Depends(session, scope="function")):
    obj = get(db, Wishlist, wish_id)
    expect(obj.user_id == user.id, "无权操作", 403)
    changes = body.model_dump(exclude_unset=True, exclude={"version"})
    room = changes.get('room', obj.room)
    duplicate = db.query(Wishlist.id).filter(Wishlist.user_id == user.id, Wishlist.sku_id == obj.sku_id, Wishlist.room == room, Wishlist.id != wish_id).first()
    expect(not duplicate, "目标房间已有此规格，请编辑已有清单项", 409)
    result = db.execute(update(Wishlist).where(Wishlist.id == wish_id, Wishlist.version == body.version)
                        .values(**changes, version=Wishlist.version + 1))
    expect(result.rowcount == 1, "清单已在其他设备修改，请刷新后核对；本次草稿未保存", 409)
    db.flush(); db.refresh(obj)
    return wish_view(db, obj)


@router.delete("/wishlist/{wish_id}")
def remove_wish(wish_id: int, user=Depends(require("customer")), db: Session = Depends(session, scope="function")):
    obj = get(db, Wishlist, wish_id); expect(obj.user_id == user.id, "无权操作", 403); db.delete(obj)
    return {"deleted": True}


class ReviewIn(BaseModel):
    order_id: int
    sku_id: int
    text: str = Field(min_length=1, max_length=3000)
    media_ids: list[str] = Field(default_factory=list, max_length=9)


@router.post("/reviews", status_code=201)
def add_review(body: ReviewIn, user=Depends(require("customer")), db: Session = Depends(session, scope="function")):
    obj = accessible_order(db, user, body.order_id)
    expect(obj.status == "completed", "签收后可评价")
    expect(db.query(OrderLine).filter_by(order_id=obj.id, sku_id=body.sku_id).first(), "规格不属于该订单")
    expect(not db.query(Review).filter_by(order_id=obj.id, sku_id=body.sku_id, user_id=user.id).first(), "已评价", 409)
    owned_media(db, user, body.media_ids, ["review"])
    review = Review(user_id=user.id, **body.model_dump()); db.add(review); db.flush()
    notify_staff(db, "operations", f"新商品评价 #{review.id}", "reviews")
    return view(review)


@router.get("/reviews")
def reviews(sku_id: int | None = None, db: Session = Depends(session, scope="function")):
    rows = db.query(Review).filter_by(deleted=False)
    if sku_id: rows = rows.filter_by(sku_id=sku_id)
    return [view(x, exclude=("user_id", "order_id")) for x in rows.order_by(Review.id.desc()).limit(100)]


class ReplyIn(BaseModel):
    reply: str = Field(default="", max_length=3000)
    deleted: bool = False


@router.patch("/reviews/{review_id}")
def reply_review(review_id: int, body: ReplyIn, user=Depends(require("admin", "staff", module="operations")), db: Session = Depends(session, scope="function")):
    obj = get(db, Review, review_id); obj.reply, obj.deleted = body.reply, body.deleted
    audit(db, user, "review.moderate", obj.id, body.model_dump())
    if body.reply: notify(db, obj.user_id, f"您的评价收到回复：{body.reply}", "orders")
    return view(obj)


class TicketIn(BaseModel):
    order_id: int
    line_id: int
    quantity: int = Field(ge=1, le=100000)
    category: Literal["damaged", "missing", "wrong", "other"]
    description: str = Field(min_length=3, max_length=3000)
    media_ids: list[str] = Field(default_factory=list, max_length=9)


@router.post("/tickets", status_code=201)
def add_ticket(body: TicketIn, user=Depends(require("customer")), db: Session = Depends(session, scope="function")):
    obj = accessible_order(db, user, body.order_id)
    expect(obj.status in ["fulfilling", "completed"], "履约开始后可申请售后")
    line = get(db, OrderLine, body.line_id)
    expect(line.order_id == obj.id and body.quantity <= line.quantity, "售后商品或数量无效")
    # Lock the common order line before summing, including on SQLite.
    db.execute(update(OrderLine).where(OrderLine.id == line.id).values(shipped_quantity=OrderLine.shipped_quantity))
    used = db.query(func.coalesce(func.sum(Ticket.quantity), 0)).filter(Ticket.line_id == line.id).scalar()
    expect(used + body.quantity <= line.quantity, "累计售后数量超过购买数量，请在原工单补充或联系客户服务", 409)
    owned_media(db, user, body.media_ids, ["ticket"])
    ticket = Ticket(user_id=user.id, **body.model_dump(), history=[{"at": now().isoformat(), "by": user.name, "status": "open", "note": body.description}])
    db.add(ticket); db.flush(); notify_staff(db, "orders", f"售后待处理 #{ticket.id}", "tickets")
    return view(ticket)


@router.get("/tickets")
def tickets(user=Depends(current_user), db: Session = Depends(session, scope="function")):
    rows = db.query(Ticket)
    if user.role == "customer": rows = rows.filter_by(user_id=user.id)
    else: expect(user.role == "admin" or user.role == "staff" and "orders" in user.permissions, "无权访问", 403)
    return [view(x) for x in rows.order_by(Ticket.id.desc())]


class TicketUpdate(BaseModel):
    status: Literal["processing", "need_information", "resolved", "closed"]
    note: str = Field(min_length=1, max_length=3000)


@router.patch("/tickets/{ticket_id}")
def update_ticket(ticket_id: int, body: TicketUpdate, user=Depends(require("admin", "staff", module="orders")), db: Session = Depends(session, scope="function")):
    obj = get(db, Ticket, ticket_id)
    transitions = {"open": ["processing", "need_information"], "processing": ["need_information", "resolved"], "need_information": ["processing", "resolved"], "resolved": ["closed", "processing"], "closed": []}
    expect(body.status in transitions[obj.status], "不允许的售后状态迁移", 409)
    obj.status = body.status
    obj.history = obj.history + [{"at": now().isoformat(), "by": user.name, **body.model_dump()}]
    notify(db, obj.user_id, f"售后 #{obj.id}：{body.note}", "tickets"); audit(db, user, "ticket.update", obj.id, body.model_dump())
    return view(obj)


class TicketSupplement(BaseModel):
    note: str = Field(min_length=1, max_length=3000)
    media_ids: list[str] = Field(default_factory=list, max_length=9)


@router.post("/tickets/{ticket_id}/supplement")
def supplement(ticket_id: int, body: TicketSupplement, user=Depends(require("customer")), db: Session = Depends(session, scope="function")):
    obj = get(db, Ticket, ticket_id); expect(obj.user_id == user.id, "无权操作", 403)
    expect(obj.status == "need_information", "当前不需要补充资料", 409)
    owned_media(db, user, body.media_ids, ["ticket"])
    obj.status = "processing"; obj.media_ids = obj.media_ids + body.media_ids
    obj.history = obj.history + [{"at": now().isoformat(), "by": user.name, "status": "processing", "note": body.note}]
    return view(obj)


@router.get("/notifications")
def notifications(user=Depends(current_user), db: Session = Depends(session, scope="function")):
    return [view(n) for n in db.query(Notification).filter_by(user_id=user.id).order_by(Notification.id.desc()).limit(100)]


@router.post("/notifications/{notification_id}/read")
def read_notification(notification_id: int, user=Depends(current_user), db: Session = Depends(session, scope="function")):
    obj = get(db, Notification, notification_id); expect(obj.user_id == user.id, "无权操作", 403); obj.read = True
    return {"read": True}


@router.get("/settings")
def settings(db: Session = Depends(session, scope="function")):
    return {x.key: x.value for x in db.query(Setting)}


class Banner(BaseModel):
    image: str
    title: str = Field(default="", max_length=100)
    link: str = Field(default="", max_length=300)


class Support(BaseModel):
    image: str
    nickname: str = Field(min_length=1, max_length=80)


class SettingsIn(BaseModel):
    customer_banners: list[Banner] = Field(min_length=1, max_length=6)
    merchant_banners: list[Banner] = Field(min_length=1, max_length=6)
    support: list[Support] = Field(min_length=1, max_length=6)


@router.put("/settings")
def save_settings(body: SettingsIn, user=Depends(require("admin", "staff", module="operations")), db: Session = Depends(session, scope="function")):
    for banner in body.customer_banners + body.merchant_banners:
        expect(not banner.link or banner.link.startswith("/product/"), "轮播链接仅支持站内商品详情")
    for key, rows in body.model_dump().items():
        for row in rows:
            owned_media(db, user, [row["image"]], ["support"] if key == "support" else ["banner", "product"])
        db.merge(Setting(key=key, value=rows))
    audit(db, user, "settings.update", "operations")
    return body.model_dump()


@router.get("/admin/dashboard")
def dashboard(user=Depends(require("admin", "staff", module="reports")), db: Session = Depends(session, scope="function")):
    rows = db.query(Order).all()
    return {"products": db.query(Product).filter_by(status="active").count(), "orders": len(rows), "confirmed_sales": sum(x.total for x in rows if x.status not in ["cancelled", "awaiting_confirmation"]), "pending_quotes": db.query(Quote).filter_by(status="pending", deleted=False).count(), "open_tickets": db.query(Ticket).filter(Ticket.status.in_(["open", "processing", "need_information"])).count(), "searches": db.query(SearchLog).count(), "no_result_searches": sum(not x.results for x in db.query(SearchLog)), "order_statuses": {s: sum(x.status == s for x in rows) for s in ["awaiting_confirmation", "confirmed", "fulfilling", "completed", "cancelled"]}}


@router.get("/admin/exceptions")
def exceptions(user=Depends(require("admin", "staff", module="reports")), db: Session = Depends(session, scope="function")):
    result = []
    for p in db.query(Procurement).filter_by(status="exception"): result.append({"kind": "procurement", "id": p.id, "message": f"订单 {p.order_id} 采购无可行方案", "owner": "采购员", "status": p.status, "created_at": p.planned_at})
    for t in db.query(Ticket).filter(Ticket.status.in_(["open", "need_information"])): result.append({"kind": "ticket", "id": t.id, "message": t.description, "owner": "客服", "status": t.status, "created_at": t.created_at})
    for t in db.query(IndexTask).filter_by(status="failed"): result.append({"kind": "index", "id": t.id, "message": t.error, "owner": "商品管理员", "status": t.status, "created_at": t.created_at})
    for o in db.query(Order).filter_by(status="fulfilling"):
        lines = db.query(OrderLine).filter_by(order_id=o.id).all()
        if any(l.shipped_quantity for l in lines) and any(l.shipped_quantity < l.quantity for l in lines):
            result.append({"kind": "partial_shipment", "id": o.id, "message": f"{o.number} 部分发货", "owner": "发货员", "status": "partial", "created_at": o.created_at})
    return result


@router.get("/admin/audits")
def audits(user=Depends(require("admin", "staff", module="reports")), db: Session = Depends(session, scope="function")):
    return [view(x) for x in db.query(Audit).order_by(Audit.id.desc()).limit(200)]


@router.get("/admin/search-logs")
def search_logs(user=Depends(require("admin", "staff", module="reports")), db: Session = Depends(session, scope="function")):
    return [view(x) for x in db.query(SearchLog).order_by(SearchLog.id.desc()).limit(100)]
