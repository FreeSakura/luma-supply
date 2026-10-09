"""Provision a management TOTP secret in a local file, outside the repository."""
import argparse
import base64
import json
import os
import secrets
from pathlib import Path
from urllib.parse import quote
from backend.db import SessionLocal
from backend.models import User, LoginSession


def provision(username, output, rotate=False):
    output = Path(output)
    data = json.loads(output.read_text(encoding='utf-8')) if output.exists() else {}
    with SessionLocal() as db:
        user = db.query(User).filter_by(username=username, active=True).first()
        if not user or user.role not in ('admin', 'staff'): raise ValueError('Choose an active management account')
        if str(user.id) in data and not rotate: raise ValueError('Already configured; use --rotate to replace the secret')
        secret = base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')
        data[str(user.id)] = secret
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(data, indent=2), encoding='utf-8')
        os.chmod(output, 0o600)
        db.query(LoginSession).filter_by(user_id=user.id).delete(); db.commit()
    return f'otpauth://totp/{quote("LumaSupply:" + username)}?secret={secret}&issuer=LumaSupply&digits=6&period=30'


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--user', required=True)
    parser.add_argument('--output', type=Path, default=Path('local-only/security/mfa.json'))
    parser.add_argument('--rotate', action='store_true')
    args=parser.parse_args()
    uri=provision(args.user, args.output, args.rotate)
    print('Set MFA_SECRETS_FILE to:', args.output.resolve())
    print('Import this private URI into your authenticator:', uri)
