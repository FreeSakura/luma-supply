"""Customer/service collaboration around an immutable inquiry snapshot."""
from typing import Literal
import json
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import update
from sqlalchemy.orm import Session
from .db import session
from .models import Inquiry, InquiryBrief, InquirySubmission, User
from .common import expect
from .security import current_user, require, audit, notify, notify_staff, digest
from .inquiry_service import (InquiryIn, InquirySubmit, prepare_inquiry, inquiry_view, accessible_inquiry,
                              add_inquiry_event, inquiry_detail)

router = APIRouter(prefix='/api')


@router.post('/inquiries/preview')
def preview_inquiry(body: InquiryIn, user=Depends(require('customer')), db: Session = Depends(session, scope="function")):
    return prepare_inquiry(db, user, body)


@router.post('/inquiries', status_code=201)
def create_inquiry(body: InquirySubmit, user=Depends(require('customer')), db: Session = Depends(session, scope="function")):
    # Serialize creation per customer so simultaneous retries return the same result.
    db.execute(update(User).where(User.id == user.id).values(active=User.active))
    signature = digest(json.dumps(body.model_dump(mode='json', exclude={'submission_key'}), sort_keys=True))
    previous = db.query(InquirySubmission).filter_by(user_id=user.id, submission_key=body.submission_key).first()
    if previous:
        expect(previous.request_hash == signature, '提交标识已用于其他需求，请重新预览', 409)
        return inquiry_view(db, db.get(Inquiry, previous.inquiry_id))
    prepared = prepare_inquiry(db, user, body)
    expect(prepared['can_submit'], '清单中有未上架商品，请调整选择后再提交', 409)
    inquiry = Inquiry(user_id=user.id, items=prepared['items'], message=body.message)
    db.add(inquiry); db.flush()
    db.add(InquirySubmission(user_id=user.id, submission_key=body.submission_key, request_hash=signature, inquiry_id=inquiry.id))
    db.add(InquiryBrief(inquiry_id=inquiry.id, requirements=prepared['requirements'], estimate=prepared['estimate']))
    add_inquiry_event(db, inquiry, user, 'submitted', body.message)
    notify_staff(db, 'orders', f'新的清单询价 #{inquiry.id}', 'inquiries')
    db.flush()
    return inquiry_view(db, inquiry)


@router.get('/inquiries')
def inquiries(status: Literal['open', 'ordered', 'withdrawn', 'closed'] | None = Query(None),
              user=Depends(current_user), db: Session = Depends(session, scope="function")):
    rows = db.query(Inquiry)
    if user.role == 'customer': rows = rows.filter_by(user_id=user.id)
    else: expect(user.role == 'admin' or user.role == 'staff' and 'orders' in user.permissions, '无权访问', 403)
    if status: rows = rows.filter_by(status=status)
    items = rows.order_by(Inquiry.id.desc()).all()
    briefs = {b.inquiry_id: b for b in db.query(InquiryBrief).filter(InquiryBrief.inquiry_id.in_([i.id for i in items]))} if items else {}
    return [inquiry_view(db, item, briefs) for item in items]


@router.get('/inquiries/{inquiry_id}')
def detail(inquiry_id: int, user=Depends(current_user), db: Session = Depends(session, scope="function")):
    return inquiry_detail(db, accessible_inquiry(db, user, inquiry_id))


class InquiryMessage(BaseModel):
    message: str = Field(min_length=1, max_length=2000)

    @field_validator('message')
    @classmethod
    def meaningful_message(cls, value):
        value = value.strip()
        if not value: raise ValueError('请填写具体内容')
        return value


def claim_open(db, inquiry, status='open'):
    # A conditional write serializes replies, withdrawal, closure and conversion.
    # SQLAlchemy configures matched-row counts, including MySQL's FOUND_ROWS flag.
    result = db.execute(update(Inquiry).where(Inquiry.id == inquiry.id, Inquiry.status == 'open',
                                              Inquiry.order_id.is_(None)).values(status=status))
    expect(result.rowcount == 1, '询价已转单、撤回或关闭，请刷新处理记录', 409)


@router.post('/inquiries/{inquiry_id}/messages', status_code=201)
def reply(inquiry_id: int, body: InquiryMessage, user=Depends(current_user), db: Session = Depends(session, scope="function")):
    inquiry = accessible_inquiry(db, user, inquiry_id)
    claim_open(db, inquiry)
    action = 'customer_message' if user.role == 'customer' else 'service_reply'
    add_inquiry_event(db, inquiry, user, action, body.message)
    if user.role == 'customer':
        notify_staff(db, 'orders', f'询价 #{inquiry.id} 有客户补充信息', 'inquiries')
    else:
        notify(db, inquiry.user_id, f'询价 #{inquiry.id} 收到客服回复', 'inquiries')
    audit(db, user, f'inquiry.{action}', inquiry.id)
    db.flush()
    return inquiry_detail(db, inquiry)


@router.post('/inquiries/{inquiry_id}/withdraw')
def withdraw(inquiry_id: int, body: InquiryMessage, user=Depends(require('customer')), db: Session = Depends(session, scope="function")):
    inquiry = accessible_inquiry(db, user, inquiry_id)
    claim_open(db, inquiry, 'withdrawn')
    add_inquiry_event(db, inquiry, user, 'withdrawn', body.message)
    notify_staff(db, 'orders', f'客户已撤回询价 #{inquiry.id}', 'inquiries')
    audit(db, user, 'inquiry.withdraw', inquiry.id)
    db.flush(); db.refresh(inquiry)
    return inquiry_detail(db, inquiry)


@router.post('/inquiries/{inquiry_id}/close')
def close(inquiry_id: int, body: InquiryMessage, user=Depends(require('admin', 'staff', module='orders')), db: Session = Depends(session, scope="function")):
    inquiry = accessible_inquiry(db, user, inquiry_id)
    claim_open(db, inquiry, 'closed')
    add_inquiry_event(db, inquiry, user, 'closed', body.message)
    notify(db, inquiry.user_id, f'询价 #{inquiry.id} 已关闭，请查看处理原因', 'inquiries')
    audit(db, user, 'inquiry.close', inquiry.id)
    db.flush(); db.refresh(inquiry)
    return inquiry_detail(db, inquiry)
