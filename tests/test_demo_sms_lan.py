import pytest
from fastapi import HTTPException, Request

from backend.accounts import PhoneIn, send_code
from backend.db import SessionLocal


def request_from(host):
    return Request({'type': 'http', 'method': 'POST', 'path': '/api/auth/code', 'headers': [], 'client': (host, 8000)})


def test_local_demo_sms_requires_explicit_flag_and_development(client, monkeypatch):
    monkeypatch.delenv('SMS_ENDPOINT', raising=False)
    monkeypatch.delenv('DEMO_SMS_LAN', raising=False)
    with SessionLocal() as db, pytest.raises(HTTPException) as blocked:
        send_code(PhoneIn(phone='13800000001'), request_from('192.168.1.20'), db)
    assert blocked.value.status_code == 503

    monkeypatch.setenv('DEMO_SMS_LAN', '1')
    with SessionLocal() as db:
        result = send_code(PhoneIn(phone='13800000002'), request_from('192.168.1.20'), db)
    assert result['mode'] == 'local-development'
    assert len(result['development_code']) == 6

    monkeypatch.setenv('APP_ENV', 'production')
    with SessionLocal() as db, pytest.raises(HTTPException) as blocked:
        send_code(PhoneIn(phone='13800000003'), request_from('192.168.1.20'), db)
    assert blocked.value.status_code == 503


def test_local_demo_sms_rejects_public_sources(client, monkeypatch):
    monkeypatch.setenv('DEMO_SMS_LAN', '1')
    monkeypatch.delenv('SMS_ENDPOINT', raising=False)
    with SessionLocal() as db, pytest.raises(HTTPException) as blocked:
        send_code(PhoneIn(phone='13800000004'), request_from('8.8.8.8'), db)
    assert blocked.value.status_code == 503
