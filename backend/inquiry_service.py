from datetime import date
from datetime import timedelta
from pydantic import BaseModel, Field, field_validator
from .models import Wishlist, SKU, Product, Inquiry, InquiryBrief, InquiryEvent, now
from .catalog import sku_view
from .common import get, expect, view


class InquiryRequirements(BaseModel):
    project_name: str = Field(default="", max_length=100)
    budget: int | None = Field(default=None, gt=0, le=10_000_000_000)
    needed_by: date | None = None
    destination: str = Field(default="", max_length=150)
    allow_alternatives: bool = False

    @field_validator('project_name', 'destination')
    @classmethod
    def strip_text(cls, value):
        return value.strip()

    @field_validator('needed_by')
    @classmethod
    def future_date(cls, value):
        if value is not None and value < (now() + timedelta(hours=8)).date():
            raise ValueError('期望到货日期不能早于今天')
        return value


class InquiryIn(BaseModel):
    wishlist_ids: list[int] = Field(min_length=1, max_length=50)
    message: str = Field(default="", max_length=3000)
    requirements: InquiryRequirements = Field(default_factory=InquiryRequirements)


class InquirySubmit(InquiryIn):
    submission_key: str = Field(min_length=8, max_length=100)


def prepare_inquiry(db, user, body):
    items, issues, rooms = [], [], {}
    for wid in dict.fromkeys(body.wishlist_ids):
        wish = get(db, Wishlist, wid)
        expect(wish.user_id == user.id, "清单不属于当前客户", 403)
        sku = get(db, SKU, wish.sku_id)
        product = get(db, Product, sku.product_id)
        snapshot = sku_view(db, sku)
        snapshot['product_name'] = product.name
        amount = snapshot['price'] * wish.quantity
        items.append({'wishlist_id': wid, 'sku_id': sku.id, 'quantity': wish.quantity,
                      'room': wish.room, 'note': wish.note, 'snapshot': snapshot,
                      'unit_price': snapshot['price'], 'line_amount': amount})
        room = rooms.setdefault(wish.room, {'room': wish.room, 'line_count': 0, 'quantity': 0, 'amount': 0})
        room['line_count'] += 1; room['quantity'] += wish.quantity; room['amount'] += amount
        if product.status != 'active' or sku.status != 'active':
            issues.append({'sku_id': sku.id, 'code': 'not_published', 'blocking': True,
                           'message': f'{sku.code} 已下架或待审核，请取消勾选'})
        elif sku.stock_status != 'available':
            issues.append({'sku_id': sku.id, 'code': 'stock_to_confirm', 'blocking': False,
                           'message': f'{sku.code} 供货状态需要客服确认'})
        missing = [label for label, value in [('尺寸', sku.size_mm), ('功率', sku.attributes.get('power_w')),
                                             ('色温', sku.attributes.get('cct_k'))] if value in (None, '')]
        if missing:
            issues.append({'sku_id': sku.id, 'code': 'missing_parameters', 'blocking': False,
                           'message': f'{sku.code} 待补充：{"、".join(missing)}'})
    total = sum(item['line_amount'] for item in items)
    budget = body.requirements.budget
    estimate = {'item_count': len(items), 'quantity': sum(i['quantity'] for i in items),
                'goods_amount': total, 'currency': 'CNY', 'rooms': list(rooms.values()),
                'budget': budget, 'over_budget': budget is not None and total > budget,
                'budget_gap': max(0, total - budget) if budget is not None else 0,
                'captured_at': now().isoformat(), 'excludes': ['shipping', 'installation'],
                'issues': issues}
    return {'items': items, 'requirements': body.requirements.model_dump(mode='json'),
            'estimate': estimate, 'can_submit': not any(issue['blocking'] for issue in issues)}


def inquiry_view(db, inquiry, briefs=None):
    brief = briefs.get(inquiry.id) if briefs is not None else db.get(InquiryBrief, inquiry.id)
    return {**view(inquiry), 'requirements': brief.requirements if brief else {},
            'estimate': brief.estimate if brief else None}


def accessible_inquiry(db, user, inquiry_id):
    inquiry = get(db, Inquiry, inquiry_id)
    permitted = (user.role == 'customer' and inquiry.user_id == user.id
                 or user.role == 'admin'
                 or user.role == 'staff' and 'orders' in user.permissions)
    expect(permitted, '无权访问此询价', 403)
    return inquiry


def add_inquiry_event(db, inquiry, user, action, message=''):
    db.add(InquiryEvent(inquiry_id=inquiry.id, actor_id=user.id, actor_name=user.name,
                        actor_role=user.role, action=action, message=message))


def inquiry_detail(db, inquiry):
    history = db.query(InquiryEvent).filter_by(inquiry_id=inquiry.id).order_by(InquiryEvent.id).all()
    return {**inquiry_view(db, inquiry),
            'history': [view(event, exclude=('actor_id',)) for event in history]}
