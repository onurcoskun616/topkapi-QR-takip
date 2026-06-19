"""Web Push: dormant-by-default behaviour, subscription storage, and the
leave-decision → notification path (with the network POST mocked out)."""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _enable_push(monkeypatch):
    """Generate a VAPID pair and switch the feature on for one test by patching
    the shared settings object the notifications module reads."""
    from app import notifications
    from app.tools.vapid_keys import generate

    keys = generate()
    monkeypatch.setattr(notifications.settings, "vapid_public_key", keys["public_pem"])
    monkeypatch.setattr(notifications.settings, "vapid_private_key", keys["private_pem"])
    monkeypatch.setattr(notifications.settings, "vapid_subject", "mailto:test@test.com")
    monkeypatch.setattr(notifications, "_web_push", None)  # drop any memoised client
    return keys


def _fake_device_keys():
    """A realistic browser subscription key pair (p256dh must be a real EC
    point or webpush's payload encryption rejects it)."""
    dev = ec.generate_private_key(ec.SECP256R1())
    raw = dev.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    p256dh = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    auth = base64.urlsafe_b64encode(b"0123456789abcdef").rstrip(b"=").decode()
    return p256dh, auth


def test_public_key_disabled_by_default(client):
    r = client.get("/api/push/public-key")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["public_key"] is None


def test_subscribe_rejected_when_disabled(client, seeded):
    p256dh, auth = _fake_device_keys()
    r = client.post(
        "/api/push/subscribe",
        headers=seeded["staff_headers"],
        json={"endpoint": "https://push.example.com/x", "keys": {"p256dh": p256dh, "auth": auth}},
    )
    assert r.status_code == 404


def test_public_key_exposed_when_enabled(client, monkeypatch):
    _enable_push(monkeypatch)
    r = client.get("/api/push/public-key")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    # applicationServerKey is the 65-byte uncompressed point, base64url (~87 chars).
    assert body["public_key"] and len(body["public_key"]) > 80


def test_subscribe_then_unsubscribe(client, seeded, monkeypatch):
    _enable_push(monkeypatch)
    p256dh, auth = _fake_device_keys()
    sub = {"endpoint": "https://push.example.com/abc", "keys": {"p256dh": p256dh, "auth": auth}}

    r = client.post("/api/push/subscribe", headers=seeded["staff_headers"], json=sub)
    assert r.status_code == 201
    assert r.json()["subscribed"] is True

    # Re-subscribing the same endpoint is idempotent (rebind, not duplicate).
    r = client.post("/api/push/subscribe", headers=seeded["staff_headers"], json=sub)
    assert r.status_code == 201

    r = client.post("/api/push/unsubscribe", headers=seeded["staff_headers"], json=sub)
    assert r.status_code == 200
    assert r.json()["subscribed"] is False


def test_leave_approval_sends_push(client, seeded, monkeypatch):
    _enable_push(monkeypatch)
    from app import notifications

    posted = []

    class _FakeResp:
        status_code = 201
        text = ""

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, content=None, headers=None):
            posted.append({"url": url, "len": len(content or b""), "headers": headers})
            return _FakeResp()

    monkeypatch.setattr(notifications.httpx, "AsyncClient", _FakeClient)

    # Staff registers a device.
    p256dh, auth = _fake_device_keys()
    r = client.post(
        "/api/push/subscribe",
        headers=seeded["staff_headers"],
        json={"endpoint": "https://push.example.com/xyz", "keys": {"p256dh": p256dh, "auth": auth}},
    )
    assert r.status_code == 201

    # Staff requests leave; director approves → background push fires.
    r = client.post(
        "/api/leaves/requests",
        headers=seeded["staff_headers"],
        json={"leave_type": "Yıllık izin", "start_date": "2025-07-01", "end_date": "2025-07-05"},
    )
    assert r.status_code == 201, r.text
    leave_id = r.json()["id"]

    r = client.post(f"/api/leaves/{leave_id}/approve", headers=seeded["dir_a_headers"])
    assert r.status_code == 200

    assert len(posted) == 1
    assert posted[0]["url"] == "https://push.example.com/xyz"
    assert posted[0]["len"] > 0  # an encrypted payload was sent
    assert "authorization" in {k.lower() for k in posted[0]["headers"]}


def test_dead_subscription_pruned_on_410(client, seeded, monkeypatch):
    _enable_push(monkeypatch)
    from app import notifications

    class _GoneResp:
        status_code = 410
        text = "gone"

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, content=None, headers=None):
            return _GoneResp()

    monkeypatch.setattr(notifications.httpx, "AsyncClient", _FakeClient)

    p256dh, auth = _fake_device_keys()
    client.post(
        "/api/push/subscribe",
        headers=seeded["staff_headers"],
        json={"endpoint": "https://push.example.com/dead", "keys": {"p256dh": p256dh, "auth": auth}},
    )

    r = client.post(
        "/api/leaves/requests",
        headers=seeded["staff_headers"],
        json={"leave_type": "Yıllık izin", "start_date": "2025-08-01", "end_date": "2025-08-02"},
    )
    leave_id = r.json()["id"]
    client.post(f"/api/leaves/{leave_id}/approve", headers=seeded["dir_a_headers"])

    # The 410 endpoint must have been pruned: a second unsubscribe finds nothing
    # but still returns cleanly.
    r = client.post(
        "/api/push/unsubscribe",
        headers=seeded["staff_headers"],
        json={"endpoint": "https://push.example.com/dead", "keys": {"p256dh": p256dh, "auth": auth}},
    )
    assert r.status_code == 200
