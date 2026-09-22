import hashlib
import secrets
from datetime import timedelta
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from .db import session
from .models import User, LoginSession, Audit, Notification, now

bearer = HTTPBearer(auto_error=False)
MODULES = ["users", "merchants", "catalog", "quotes", "orders", "procurement", "operations", "reports"]


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(value: str):
    salt = secrets.token_hex(16)
    key = hashlib.scrypt(value.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return f"scrypt${salt}${key}"


def password_valid(value: str, stored: str):
    _, salt, key = stored.split("$")
    candidate = hashlib.scrypt(value.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return secrets.compare_digest(candidate, key)


def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(session)):
    if not credentials:
        raise HTTPException(401, "请先登录 / Sign in required")
    login = db.get(LoginSession, digest(credentials.credentials))
    user = db.get(User, login.user_id) if login and login.expires_at > now() else None
    if not user or not user.active:
        raise HTTPException(401, "登录已失效 / Session expired")
    return user


def require(*roles, module=None):
    def check(user: User = Depends(current_user)):
        if user.role not in roles or (user.role == "staff" and module and module not in user.permissions):
            raise HTTPException(403, "无权访问此功能 / Access denied")
        return user
    return check


def issue_session(db, user):
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=digest(token), user_id=user.id, expires_at=now() + timedelta(days=7)))
    return {"token": token, "user": user_view(user)}


def user_view(user):
    return {"id": user.id, "username": user.username, "name": user.name, "phone": user.phone, "role": user.role, "permissions": MODULES if user.role == "admin" else user.permissions, "active": user.active}


def audit(db, user, action, target, details=None):
    db.add(Audit(user_id=user.id, action=action, target=str(target), details=details or {}))


def notify(db, user_id, message, link=""):
    db.add(Notification(user_id=user_id, message=message, link=link))


def notify_staff(db, module, message, link=""):
    for user in db.query(User).filter(User.active.is_(True), User.role.in_(["admin", "staff"])):
        if user.role == "admin" or module in user.permissions:
            notify(db, user.id, message, link)
