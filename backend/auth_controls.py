"""Database-backed throttling and RFC 6238 TOTP; secrets stay in deployment config."""
import base64
import hashlib
import hmac
import json
import os
import struct
import time
from datetime import timedelta
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import case, update
from .models import LoginAttempt, TotpUse, now


def upsert(db, model, values, updates):
    if db.bind.dialect.name == 'sqlite':
        from sqlalchemy.dialects.sqlite import insert
        stmt = insert(model).values(**values).on_conflict_do_update(
            index_elements=[c.name for c in model.__table__.primary_key], set_=updates)
    else:
        from sqlalchemy.dialects.mysql import insert
        stmt = insert(model).values(**values).on_duplicate_key_update(**updates)
    db.execute(stmt)


def bucket_key(scope, identity):
    return hashlib.sha256(f'{scope}:{identity}'.encode()).hexdigest()


def consume(db, scope, identity, seconds):
    key = bucket_key(scope, identity); instant = now(); cutoff = instant - timedelta(seconds=seconds)
    expired = LoginAttempt.window_start <= cutoff
    upsert(db, LoginAttempt, {'key': key, 'failures': 1, 'window_start': instant},
           {'failures': case((expired, 1), else_=LoginAttempt.failures + 1),
            'window_start': case((expired, instant), else_=LoginAttempt.window_start)})
    return db.query(LoginAttempt).populate_existing().filter_by(key=key).one()


def source_limit(db, request, scope='login'):
    limit = int(os.getenv('AUTH_SOURCE_LIMIT', '100')) if scope == 'login' else int(os.getenv('SMS_SOURCE_LIMIT', '20'))
    record = consume(db, 'source:' + scope, request.client.host, 300)
    count = record.failures
    db.commit()  # Count attempted requests even if downstream authentication fails.
    if count > limit:
        raise HTTPException(429, '请求过于频繁，请稍后重试', headers={'Retry-After': '300'})


def account_limit(db, identity):
    record = db.get(LoginAttempt, bucket_key('account', identity))
    if record and record.window_start > now() - timedelta(minutes=10) and record.failures >= int(os.getenv('AUTH_FAILURE_LIMIT', '5')):
        raise HTTPException(429, '登录失败次数过多，请 10 分钟后重试', headers={'Retry-After': '600'})


def login_failed(db, identity):
    consume(db, 'account', identity, 600); db.commit()


def login_succeeded(db, identity):
    db.query(LoginAttempt).filter_by(key=bucket_key('account', identity)).delete()


def configured_secret(user):
    try:
        raw = os.getenv('MFA_TOTP_SECRETS', '')
        if not raw and os.getenv('MFA_SECRETS_FILE'):
            raw = Path(os.environ['MFA_SECRETS_FILE']).read_text(encoding='utf-8')
        secrets = json.loads(raw or '{}')
        if not isinstance(secrets, dict): raise ValueError()
        return secrets.get(str(user.id)) or secrets.get(user.username)
    except (ValueError, OSError):
        raise HTTPException(503, '管理员验证配置不可用，请联系运维') from None


def requires_mfa(user):
    return bool(configured_secret(user)) or (user.role == 'admin' and os.getenv('APP_ENV') == 'production')


def totp(secret, step, digits=6):
    key = base64.b32decode(secret.upper() + '=' * (-len(secret) % 8))
    value = hmac.new(key, struct.pack('>Q', step), hashlib.sha1).digest()
    offset = value[-1] & 15
    return str((struct.unpack('>I', value[offset:offset + 4])[0] & 0x7fffffff) % (10 ** digits)).zfill(digits)


def verify_mfa(db, user, code):
    secret = configured_secret(user)
    if not requires_mfa(user): return False
    if not secret: raise HTTPException(503, '请先为管理员配置动态验证码')
    current = int(time.time()) // 30
    try:
        step = next((s for s in [current, current - 1, current + 1] if hmac.compare_digest(totp(secret, s), code)), None)
    except (ValueError, TypeError):
        raise HTTPException(503, '动态验证码配置无效，请联系运维') from None
    if step is None: raise HTTPException(401, '动态验证码错误或已过期')
    # Initialize once, then claim a strictly newer step with an atomic condition.
    upsert(db, TotpUse, {'user_id': user.id, 'last_step': -1}, {'user_id': user.id})
    claimed = db.execute(update(TotpUse).where(TotpUse.user_id == user.id, TotpUse.last_step < step).values(last_step=step))
    if claimed.rowcount != 1: raise HTTPException(401, '此动态验证码已使用，请等待新的验证码')
    return True
