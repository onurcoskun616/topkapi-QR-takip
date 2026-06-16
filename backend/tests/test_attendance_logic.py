"""Unit tests for the core attendance toggle + QR token rules.

Run with:  pytest   (from the backend/ directory)
"""
from datetime import datetime, timedelta, timezone

import pytest
from jose import ExpiredSignatureError

from app.models import AttendanceType
from app.security import create_qr_token, decode_qr_token
from app.services import next_attendance_type


class _FakeLog:
    def __init__(self, type_):
        self.type = type_


def test_first_scan_of_day_is_in():
    assert next_attendance_type(None) == AttendanceType.IN


def test_after_in_comes_out():
    assert next_attendance_type(_FakeLog(AttendanceType.IN)) == AttendanceType.OUT


def test_after_out_comes_in():
    assert next_attendance_type(_FakeLog(AttendanceType.OUT)) == AttendanceType.IN


def test_qr_token_roundtrip_valid():
    data = create_qr_token()
    payload = decode_qr_token(data["token"])
    assert payload["jti"] == data["jti"]
    assert payload["type"] == "kiosk_qr"


def test_expired_qr_token_rejected(monkeypatch):
    # Craft a token that already expired by patching the TTL to negative.
    from app import security

    monkeypatch.setattr(security.settings, "qr_token_ttl_seconds", -1)
    data = security.create_qr_token()
    with pytest.raises(ExpiredSignatureError):
        decode_qr_token(data["token"])


def test_qr_token_uses_server_clock_not_client(monkeypatch):
    """Token exp is derived from server UTC; a token minted 'now' is valid now."""
    data = create_qr_token()
    payload = decode_qr_token(data["token"])
    now = datetime.now(timezone.utc).timestamp()
    # exp should be within the configured TTL window ahead of now.
    assert payload["exp"] > now
    assert payload["exp"] <= now + 16  # ttl (15) + small slack
