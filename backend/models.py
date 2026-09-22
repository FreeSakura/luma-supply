from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from .db import Base


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String(40), unique=True, nullable=False)
    phone = Column(String(30), unique=True)
    password_hash = Column(String(200), nullable=False)
    role = Column(String(20), nullable=False)
    name = Column(String(80), default="")
    permissions = Column(JSON, default=list)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)


class LoginSession(Base):
    __tablename__ = "sessions"
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime, nullable=False)


class Verification(Base):
    __tablename__ = "verifications"
    phone = Column(String(30), primary_key=True)
    code_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, default=0)
    sent_at = Column(DateTime, default=now)


class Merchant(Base):
    __tablename__ = "merchants"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    shop_name = Column(String(100), nullable=False)
    legal_name = Column(String(100), default="")
    phone = Column(String(30), default="")
    address = Column(String(300), default="")
    license_media_id = Column(String(64))
    status = Column(String(20), default="pending")
    reason = Column(String(300), default="")


class Address(Base):
    __tablename__ = "addresses"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    recipient = Column(String(80), nullable=False)
    phone = Column(String(30), nullable=False)
    detail = Column(String(300), nullable=False)


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    title = Column(String(200), nullable=False)
    category = Column(String(50), nullable=False)
    description = Column(Text, default="")
    status = Column(String(20), default="active")
    owner_id = Column(Integer, ForeignKey("users.id"))
    custom = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)


class SKU(Base):
    __tablename__ = "skus"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    code = Column(String(80), unique=True, nullable=False)
    color = Column(String(40), default="")
    size_mm = Column(String(80), default="")
    specification = Column(String(150), default="")
    unit = Column(String(20), default="个")
    attributes = Column(JSON, default=dict)
    images = Column(JSON, default=list)
    initial_price = Column(Integer, nullable=False)
    manual_price = Column(Integer)
    stock_status = Column(String(20), default="available")
    status = Column(String(20), default="active")


class ProductChange(Base):
    __tablename__ = "product_changes"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    payload = Column(JSON, nullable=False)
    status = Column(String(20), default="pending")
    reason = Column(String(300), default="")
    created_at = Column(DateTime, default=now)


class Quote(Base):
    __tablename__ = "quotes"
    __table_args__ = (UniqueConstraint("merchant_id", "sku_id", "version"),)
    id = Column(Integer, primary_key=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    version = Column(Integer, nullable=False)
    price = Column(Integer, nullable=False)
    available_quantity = Column(Integer)
    reserved_quantity = Column(Integer, default=0)
    min_quantity = Column(Integer, default=1)
    lead_days = Column(Integer, default=3)
    freight = Column(Integer, default=0)
    valid_until = Column(DateTime, nullable=False)
    status = Column(String(20), default="pending")
    active = Column(Boolean, default=True)
    deleted = Column(Boolean, default=False)
    reason = Column(String(300), default="")
    created_at = Column(DateTime, default=now)


class PricingRule(Base):
    __tablename__ = "pricing_rules"
    id = Column(Integer, primary_key=True)
    multiplier_bp = Column(Integer, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=now)


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    number = Column(String(40), unique=True, nullable=False)
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    service_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    idempotency_key = Column(String(100), unique=True, nullable=False)
    request_hash = Column(String(64), nullable=False)
    status = Column(String(20), default="awaiting_confirmation")
    version = Column(Integer, default=1)
    total = Column(Integer, nullable=False)
    remark = Column(Text, default="")
    delivery_mode = Column(String(20))
    address_snapshot = Column(JSON)
    created_at = Column(DateTime, default=now)


class OrderLine(Base):
    __tablename__ = "order_lines"
    __table_args__ = (UniqueConstraint("order_id", "sku_id"),)
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Integer, nullable=False)
    snapshot = Column(JSON, nullable=False)
    shipped_quantity = Column(Integer, default=0)


class Procurement(Base):
    __tablename__ = "procurements"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), unique=True, nullable=False)
    status = Column(String(30), default="draft")
    plan = Column(JSON)
    constraints = Column(JSON, default=dict)
    planned_at = Column(DateTime)
    proof_media_ids = Column(JSON, default=list)
    version = Column(Integer, default=1)


class Shipment(Base):
    __tablename__ = "shipments"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    idempotency_key = Column(String(100), unique=True, nullable=False)
    tracking = Column(String(100), default="")
    carrier = Column(String(80), default="")
    items = Column(JSON, nullable=False)
    proof_media_ids = Column(JSON, default=list)
    received = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)


class Wishlist(Base):
    __tablename__ = "wishlist"
    __table_args__ = (UniqueConstraint("user_id", "sku_id", "room"),)
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    room = Column(String(60), default="客厅")
    quantity = Column(Integer, default=1)
    note = Column(String(300), default="")
    watch_price = Column(Boolean, default=False)
    watch_stock = Column(Boolean, default=False)


class Inquiry(Base):
    __tablename__ = "inquiries"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    items = Column(JSON, nullable=False)
    message = Column(Text, default="")
    status = Column(String(20), default="open")
    order_id = Column(Integer, ForeignKey("orders.id"))
    created_at = Column(DateTime, default=now)


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("order_id", "sku_id", "user_id"),)
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    sku_id = Column(Integer, ForeignKey("skus.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    text = Column(Text, nullable=False)
    media_ids = Column(JSON, default=list)
    reply = Column(Text, default="")
    deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)


class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    line_id = Column(Integer, ForeignKey("order_lines.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    category = Column(String(40), nullable=False)
    description = Column(Text, nullable=False)
    media_ids = Column(JSON, default=list)
    status = Column(String(20), default="open")
    history = Column(JSON, default=list)
    created_at = Column(DateTime, default=now)


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message = Column(String(500), nullable=False)
    link = Column(String(200), default="")
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(60), primary_key=True)
    value = Column(JSON, nullable=False)


class Media(Base):
    __tablename__ = "media"
    id = Column(String(64), primary_key=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    purpose = Column(String(30), nullable=False)
    mime = Column(String(80), nullable=False)
    path = Column(String(300), nullable=False)
    created_at = Column(DateTime, default=now)


class IndexTask(Base):
    __tablename__ = "index_tasks"
    id = Column(Integer, primary_key=True)
    status = Column(String(20), default="pending")
    reason = Column(String(200), nullable=False)
    attempts = Column(Integer, default=0)
    error = Column(Text, default="")
    created_at = Column(DateTime, default=now)


class Audit(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String(80), nullable=False)
    target = Column(String(100), nullable=False)
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=now)


class SearchLog(Base):
    __tablename__ = "search_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    query = Column(String(500), default="")
    results = Column(JSON, default=list)
    latency_ms = Column(Integer, nullable=False)
    model_version = Column(String(100), nullable=False)
    feedback = Column(JSON, default=list)
    created_at = Column(DateTime, default=now)
