"""Shared fixtures for integration tests.

Settings/engine are constructed at import time (``lru_cache`` + module-level
singletons), so each test that needs an isolated SQLite database re-imports
the whole ``app`` package after setting environment variables — mirroring how
the app is actually configured (env vars read once at process start).
"""
import sys

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("AUTH_SECRET", "test-auth-secret")
    monkeypatch.setenv("REFRESH_SECRET", "test-refresh-secret")
    monkeypatch.setenv("QR_SECRET", "test-qr-secret")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "hq@test.com")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "HqPassword123!")
    monkeypatch.setenv("ATTENDANCE_TIMEZONE", "Europe/Istanbul")

    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]

    from fastapi.testclient import TestClient

    from app.main import app as fastapi_app

    with TestClient(fastapi_app) as test_client:
        yield test_client


@pytest.fixture()
def seeded(client):
    """Two campuses with directors, an approved staff member at campus A, and
    campus A's shift hours set to 08:00–17:00."""
    r = client.post(
        "/api/auth/login",
        json={"email": "hq@test.com", "password": "HqPassword123!", "device_fingerprint": "hq-fp-aaaa"},
    )
    hq_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    campuses = client.get("/api/campuses").json()
    campus_a, campus_b = campuses[0], campuses[1]

    client.patch(
        f"/api/campuses/{campus_a['id']}/shift",
        headers=hq_headers,
        json={"shift_start": "08:00:00", "shift_end": "17:00:00"},
    )

    client.post(
        "/api/directors",
        headers=hq_headers,
        json={
            "full_name": "Müdür A",
            "email": "director.a@test.com",
            "password": "DirPassword123!",
            "campus_id": campus_a["id"],
        },
    )
    r = client.post(
        "/api/auth/login",
        json={"email": "director.a@test.com", "password": "DirPassword123!", "device_fingerprint": "dir-a-fp-aaaa"},
    )
    dir_a_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    client.post(
        "/api/directors",
        headers=hq_headers,
        json={
            "full_name": "Müdür B",
            "email": "director.b@test.com",
            "password": "DirPassword123!",
            "campus_id": campus_b["id"],
        },
    )
    r = client.post(
        "/api/auth/login",
        json={"email": "director.b@test.com", "password": "DirPassword123!", "device_fingerprint": "dir-b-fp-aaaa"},
    )
    dir_b_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    r = client.post(
        "/api/auth/register",
        json={
            "full_name": "Ayşe Yılmaz",
            "phone": "0532 111 22 33",
            "job_title": "Öğretmen",
            "branch": "Matematik",
            "birth_date": "1990-05-20",
            "tc_kimlik_no": "11111111042",
            "campus_id": campus_a["id"],
            "device_fingerprint": "staff-fp-bbbbbbbb",
        },
    )
    staff_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    staff_id = r.json()["user"]["id"]

    client.post(f"/api/staff/{staff_id}/approve", headers=dir_a_headers)

    return {
        "hq_headers": hq_headers,
        "dir_a_headers": dir_a_headers,
        "dir_b_headers": dir_b_headers,
        "staff_headers": staff_headers,
        "staff_id": staff_id,
        "staff_tc_kimlik_no": "11111111042",
        "campus_a": campus_a,
        "campus_b": campus_b,
    }
