import os
import secrets
from datetime import timedelta
from typing import Literal
import httpx
from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import delete, update
from .db import session
from .models import User, Merchant, Address, Verification, LoginSession, Quote, LoginAttempt, now
from .security import current_user, require, password_hash, password_valid, issue_session, digest, user_view, audit, notify, notify_staff, MODULES
from .common import get, expect, view
from .auth_controls import source_limit, account_limit, login_failed, login_succeeded, verify_mfa, consume

router = APIRouter(prefix="/api")


class PhoneIn(BaseModel):
    phone: str = Field(pattern=r"^1[3-9]\d{9}$")


class RegisterIn(PhoneIn):
    username: str = Field(min_length=2, max_length=40)
    password: str = Field(min_length=8, max_length=128)
    code: str
    role: Literal["customer", "merchant"] = "customer"
    agreement: bool


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)
    otp: str = Field(default='', max_length=8)


class ResetIn(PhoneIn):
    code: str
    password: str = Field(min_length=8, max_length=128)
    otp: str = Field(default='', max_length=8)


class CodeLogin(PhoneIn):
    code: str
    otp: str = Field(default='', max_length=8)


def verify_code(db, phone, code):
    record = db.get(Verification, phone)
    expect(record and record.expires_at > now() and record.attempts < 5, "验证码过期或未发送")
    if not secrets.compare_digest(record.code_hash, digest(code)):
        db.execute(update(Verification).where(Verification.phone == phone, Verification.attempts < 5).values(attempts=Verification.attempts + 1))
        db.commit()  # failed attempts must persist even when the request fails
        expect(False, "验证码错误")
    result = db.execute(delete(Verification).where(Verification.phone == phone, Verification.code_hash == digest(code), Verification.expires_at > now(), Verification.attempts < 5))
    expect(result.rowcount == 1, '验证码已使用或失效，请重新获取', 409)


@router.post("/auth/code")
def send_code(body: PhoneIn, request: Request, db: Session = Depends(session, scope="function")):
    source_limit(db, request, 'sms')
    previous = db.get(Verification, body.phone)
    expect(not previous or now() - previous.sent_at >= timedelta(seconds=60), "请在 60 秒后重新发送", 429)
    code = f"{secrets.randbelow(1000000):06d}"
    endpoint = os.getenv("SMS_ENDPOINT")
    development = os.getenv("APP_ENV", "development") == "development" and request.client.host in ["127.0.0.1", "::1", "testclient"]
    expect(endpoint or development, "短信服务未配置", 503)
    phone_bucket = consume(db, 'sms-phone', body.phone, 60)
    allowed = phone_bucket.failures == 1
    db.commit()
    expect(allowed, '请在 60 秒后重新发送', 429)
    if endpoint:
        try:
            with httpx.Client(timeout=10) as client:
                response = client.post(endpoint, json={"phone": body.phone, "code": code, "expires_seconds": 300}, headers={"Authorization": f"Bearer {os.getenv('SMS_TOKEN', '')}"})
                expect(response.is_success, "短信服务发送失败", 502)
        except httpx.HTTPError:
            raise HTTPException(502, '短信服务暂不可用，请稍后重试') from None
    db.merge(Verification(phone=body.phone, code_hash=digest(code), attempts=0, expires_at=now() + timedelta(minutes=5), sent_at=now()))
    return {"sent": True, "mode": "gateway" if endpoint else "local-development", "development_code": code if development and not endpoint else None}


@router.post("/auth/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(session, scope="function")):
    expect(body.agreement, "请阅读并同意注册协议与隐私说明")
    expect(not body.username.lower().startswith('wx_'), '此前缀用于微信身份，请选择其他用户名')
    expect(not db.query(User).filter((User.username == body.username) | (User.phone == body.phone)).first(), "用户名或手机号已存在", 409)
    verify_code(db, body.phone, body.code)
    user = User(username=body.username, phone=body.phone, password_hash=password_hash(body.password), role=body.role, name=body.username)
    db.add(user)
    db.flush()
    if body.role == "merchant":
        db.add(Merchant(user_id=user.id, shop_name=body.username, phone=body.phone))
    return issue_session(db, user)


@router.post("/auth/login")
def login(body: LoginIn, request: Request, db: Session = Depends(session, scope="function")):
    source_limit(db, request)
    username = body.username.strip()
    user = db.query(User).filter((User.username == username) | (User.phone == username)).first()
    identity = f'user:{user.id}' if user else 'login:' + username.lower()
    account_limit(db, identity)
    if not (user and user.active and password_valid(body.password, user.password_hash)):
        login_failed(db, identity)
        expect(False, '账户或密码不正确', 401)
    try: verified = verify_mfa(db, user, body.otp)
    except HTTPException as exc:
        if exc.status_code == 401: login_failed(db, identity)
        raise
    login_succeeded(db, identity)
    return issue_session(db, user, verified)


@router.post("/auth/login-code")
def login_code(body: CodeLogin, request: Request, db: Session = Depends(session, scope="function")):
    source_limit(db, request)
    user = db.query(User).filter_by(phone=body.phone, active=True).first()
    expect(user, "请先注册", 404)
    verified = verify_mfa(db, user, body.otp)
    verify_code(db, body.phone, body.code)
    return issue_session(db, user, verified)


@router.post("/auth/reset")
def reset(body: ResetIn, request: Request, db: Session = Depends(session, scope="function")):
    source_limit(db, request)
    user = db.query(User).filter_by(phone=body.phone, active=True).first()
    expect(user, "账户不存在", 404)
    verify_mfa(db, user, body.otp)
    verify_code(db, body.phone, body.code)
    user.password_hash = password_hash(body.password)
    db.query(LoginSession).filter_by(user_id=user.id).delete()
    return {"reset": True}


class PasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/auth/password")
def change_password(body: PasswordIn, user=Depends(current_user), db: Session = Depends(session, scope="function")):
    expect(password_valid(body.old_password, user.password_hash), "原密码错误")
    user.password_hash = password_hash(body.new_password)
    db.query(LoginSession).filter_by(user_id=user.id).delete()
    return {"changed": True}


@router.post("/auth/logout")
def logout(request: Request, user=Depends(current_user), db: Session = Depends(session, scope="function")):
    token = request.headers['authorization'].split(None, 1)[1]
    db.query(LoginSession).filter_by(token_hash=digest(token)).delete()
    return {"logged_out": True}


class ReauthIn(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    otp: str = Field(default='', max_length=8)


@router.post('/auth/reauth')
def reauthenticate(body: ReauthIn, request: Request, user=Depends(current_user), db: Session = Depends(session, scope='function')):
    source_limit(db, request)
    identity = f'user:{user.id}'; account_limit(db, identity)
    if not password_valid(body.password, user.password_hash):
        login_failed(db, identity); raise HTTPException(401, '身份验证失败')
    try: verified = verify_mfa(db, user, body.otp)
    except HTTPException as exc:
        if exc.status_code == 401: login_failed(db, identity)
        raise
    login_succeeded(db, identity)
    record = request.state.login
    record.authenticated_at = now(); record.last_seen_at = now(); record.mfa_verified = verified
    return {'verified': True, 'valid_for_seconds': 900}


@router.get("/me")
def me(user=Depends(current_user)):
    return user_view(user)


class ProfileIn(BaseModel):
    username: str = Field(min_length=2, max_length=40)
    name: str = Field(max_length=80)


@router.patch("/me")
def profile(body: ProfileIn, user=Depends(current_user), db: Session = Depends(session, scope="function")):
    expect(body.username == user.username or not body.username.lower().startswith('wx_'), '此前缀用于微信身份，请选择其他用户名')
    expect(not db.query(User).filter(User.username == body.username, User.id != user.id).first(), "用户名已存在", 409)
    user.username, user.name = body.username, body.name
    return user_view(user)


class AddressIn(BaseModel):
    recipient: str = Field(min_length=1, max_length=80)
    phone: str = Field(min_length=6, max_length=30)
    detail: str = Field(min_length=4, max_length=300)


@router.get("/addresses")
def addresses(user=Depends(current_user), db: Session = Depends(session, scope="function")):
    return [view(x) for x in db.query(Address).filter_by(user_id=user.id)]


@router.post("/addresses", status_code=201)
def add_address(body: AddressIn, user=Depends(current_user), db: Session = Depends(session, scope="function")):
    obj = Address(user_id=user.id, **body.model_dump()); db.add(obj); db.flush()
    return view(obj)


@router.delete("/addresses/{address_id}")
def delete_address(address_id: int, user=Depends(current_user), db: Session = Depends(session, scope="function")):
    obj = get(db, Address, address_id); expect(obj.user_id == user.id, "无权操作", 403); db.delete(obj)
    return {"deleted": True}


class MerchantIn(BaseModel):
    shop_name: str = Field(min_length=2, max_length=100)
    legal_name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=6, max_length=30)
    address: str = Field(min_length=4, max_length=300)
    license_media_id: str


@router.get("/merchant/profile")
def merchant_profile(user=Depends(require("merchant")), db: Session = Depends(session, scope="function")):
    return view(db.query(Merchant).filter_by(user_id=user.id).one())


@router.put("/merchant/profile")
def merchant_submit(body: MerchantIn, user=Depends(require("merchant")), db: Session = Depends(session, scope="function")):
    from .media import owned_media
    owned_media(db, user, [body.license_media_id], purposes=["license"])
    obj = db.query(Merchant).filter_by(user_id=user.id).one()
    for k, v in body.model_dump().items(): setattr(obj, k, v)
    obj.status = "pending"
    notify_staff(db, "merchants", f"商家认证待审核：{obj.shop_name}", "merchants")
    audit(db, user, "merchant.submit", obj.id)
    return view(obj)


@router.get("/admin/merchants")
def merchants(q: str = "", user=Depends(require("admin", "staff", module="merchants")), db: Session = Depends(session, scope="function")):
    rows = db.query(Merchant).filter((Merchant.shop_name.contains(q)) | (Merchant.legal_name.contains(q)) | (Merchant.phone.contains(q)))
    return [view(x) for x in rows]


class DecisionIn(BaseModel):
    approve: bool
    reason: str = Field(default="", max_length=300)


@router.post("/admin/merchants/{merchant_id}/review")
def merchant_review(merchant_id: int, body: DecisionIn, user=Depends(require("admin", "staff", module="merchants")), db: Session = Depends(session, scope="function")):
    obj = get(db, Merchant, merchant_id)
    expect(body.approve or body.reason.strip(), "驳回需要填写原因")
    expect(obj.status == "pending", "该认证已处理", 409)
    obj.status = "approved" if body.approve else "rejected"; obj.reason = body.reason
    notify(db, obj.user_id, f"认证{obj.status}：{body.reason}", "profile")
    audit(db, user, "merchant.review", obj.id, body.model_dump())
    return view(obj)


@router.post("/admin/merchants/{merchant_id}/disable")
def disable_merchant(merchant_id: int, user=Depends(require("admin", "staff", module="merchants")), db: Session = Depends(session, scope="function")):
    obj = get(db, Merchant, merchant_id); obj.status = "disabled"
    get(db, User, obj.user_id).active = False
    db.query(Quote).filter_by(merchant_id=obj.id).update({"active": False, "deleted": True})
    audit(db, user, "merchant.disable", obj.id)
    return {"disabled": True}


@router.get("/admin/users")
def users(q: str = "", role: str = "", user=Depends(require("admin", "staff", module="users")), db: Session = Depends(session, scope="function")):
    rows = db.query(User).filter((User.username.contains(q)) | (User.name.contains(q)))
    if role: rows = rows.filter_by(role=role)
    return [user_view(x) for x in rows]


class StaffIn(BaseModel):
    username: str = Field(min_length=2, max_length=40)
    name: str = Field(max_length=80)
    password: str = Field(min_length=8, max_length=128)
    permissions: list[str]


@router.post("/admin/staff", status_code=201)
def create_staff(body: StaffIn, user=Depends(require("admin")), db: Session = Depends(session, scope="function")):
    expect(set(body.permissions) <= set(MODULES), "未知权限模块")
    expect(not db.query(User).filter_by(username=body.username).first(), "用户名已存在", 409)
    obj = User(username=body.username, name=body.name, password_hash=password_hash(body.password), role="staff", permissions=body.permissions)
    db.add(obj); db.flush(); audit(db, user, "staff.create", obj.id)
    return user_view(obj)


class StaffEdit(BaseModel):
    name: str = Field(max_length=80)
    permissions: list[str]
    active: bool


@router.patch("/admin/staff/{user_id}")
def update_staff(user_id: int, body: StaffEdit, user=Depends(require("admin")), db: Session = Depends(session, scope="function")):
    obj = get(db, User, user_id); expect(obj.role == "staff", "只能修改员工账户")
    expect(set(body.permissions) <= set(MODULES), "未知权限模块")
    for k, v in body.model_dump().items(): setattr(obj, k, v)
    audit(db, user, "staff.update", obj.id, body.model_dump())
    return user_view(obj)

