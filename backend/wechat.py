"""WeChat code exchange and explicit account binding for the two mini-programs."""
import os
import secrets
from typing import Literal
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from .db import session
from .models import User, WechatIdentity
from .common import expect
from .security import require, digest, password_hash, issue_session, audit

router = APIRouter(prefix='/api')


class WechatIn(BaseModel):
    code: str = Field(min_length=1, max_length=256)
    role: Literal['customer', 'merchant'] = 'customer'
    agreement: bool = False


def exchange(body):
    prefix = 'WECHAT_MERCHANT' if body.role == 'merchant' else 'WECHAT'
    app_id, secret = os.getenv(prefix + '_APP_ID'), os.getenv(prefix + '_APP_SECRET')
    expect(app_id and secret, '此端微信登录尚未配置，请使用账号登录', 503)
    try:
        with httpx.Client(timeout=10) as client:
            response = client.get('https://api.weixin.qq.com/sns/jscode2session', params={
                'appid': app_id, 'secret': secret, 'js_code': body.code, 'grant_type': 'authorization_code'})
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, '微信身份服务暂不可用，请重试') from None
    expect(isinstance(result, dict) and result.get('openid') and not result.get('errcode'), '微信凭证无效或已使用，请重新授权', 401)
    return app_id, digest(app_id + result['openid'])


@router.post('/auth/wechat')
def login(body: WechatIn, db: Session = Depends(session, scope='function')):
    app_id, openid_hash = exchange(body)
    identity = db.query(WechatIdentity).filter_by(app_id=app_id, openid_hash=openid_hash).first()
    user = db.get(User, identity.user_id) if identity else None
    if not user:
        expect(body.role == 'customer', '请先用商家账号登录，在我的资料中绑定微信', 409)
        # Retain accounts created by the 1.7 customer login implementation.
        user = db.query(User).filter_by(username='wx_' + openid_hash[:30]).first()
        if not user:
            expect(body.agreement, '首次微信登录请同意服务与隐私说明', 400)
            user = User(username='wx_' + openid_hash[:30], name='微信用户', role='customer',
                        password_hash=password_hash(secrets.token_urlsafe(32)))
            db.add(user); db.flush()
        db.add(WechatIdentity(app_id=app_id, openid_hash=openid_hash, user_id=user.id))
    expect(user.active and user.role == body.role, '账户不可用于当前小程序', 403)
    return issue_session(db, user)


@router.post('/auth/wechat/bind')
def bind(body: WechatIn, user=Depends(require('customer', 'merchant')), db: Session = Depends(session, scope='function')):
    expect(body.role == user.role, '只能绑定当前账号对应的小程序', 403)
    app_id, openid_hash = exchange(body)
    identity = db.query(WechatIdentity).filter_by(app_id=app_id, openid_hash=openid_hash).first()
    expect(not identity or identity.user_id == user.id, '此微信已绑定其他账号，不能自动合并', 409)
    current = db.query(WechatIdentity).filter_by(app_id=app_id, user_id=user.id).first()
    expect(not current or current.openid_hash == openid_hash, '账号已绑定其他微信，请联系管理员核实', 409)
    if not identity:
        db.add(WechatIdentity(app_id=app_id, openid_hash=openid_hash, user_id=user.id))
        audit(db, user, 'wechat.bind', user.id)
    return {'bound': True, 'role': user.role}


@router.get('/me/wechat')
def binding(user=Depends(require('customer', 'merchant')), db: Session = Depends(session, scope='function')):
    return {'bound': db.query(WechatIdentity).filter_by(user_id=user.id).first() is not None, 'role': user.role}
