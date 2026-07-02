"""Security-hardening tests:

  1. Production fail-closed secret guard (assert_production_security).
  2. Login brute-force lockout (failed-attempt throttle).
  3. QR campus binding (a code shown at one campus can't be scanned elsewhere).
"""
from types import SimpleNamespace

import pytest


# --------------------------------------------------------------------------- #
# 1. Production secret guard
# --------------------------------------------------------------------------- #
def _cfg(**override):
    base = dict(
        app_env="production",
        auth_secret="a" * 32,
        refresh_secret="b" * 32,
        qr_secret="c" * 32,
        bootstrap_admin_password="A-Strong-Bootstrap-Pass-1!",
    )
    base.update(override)
    return SimpleNamespace(**base)


def test_production_guard_passes_with_strong_distinct_secrets():
    from app.config import assert_production_security

    # Should not raise.
    assert assert_production_security(_cfg()) is None


def test_production_guard_blocks_shipped_default_secret():
    from app.config import assert_production_security

    with pytest.raises(RuntimeError):
        assert_production_security(_cfg(auth_secret="change-me-auth"))


def test_production_guard_blocks_dev_placeholder_secret():
    from app.config import assert_production_security

    with pytest.raises(RuntimeError):
        assert_production_security(
            _cfg(qr_secret="dev-qr-secret-change-in-production")
        )


def test_production_guard_blocks_too_short_secret():
    from app.config import assert_production_security

    with pytest.raises(RuntimeError):
        assert_production_security(_cfg(refresh_secret="short"))


def test_production_guard_blocks_reused_secret():
    from app.config import assert_production_security

    with pytest.raises(RuntimeError):
        assert_production_security(_cfg(refresh_secret="a" * 32))  # == auth_secret


def test_production_guard_blocks_default_bootstrap_password():
    from app.config import assert_production_security

    with pytest.raises(RuntimeError):
        assert_production_security(
            _cfg(bootstrap_admin_password="ChangeThisAdminPassword123!")
        )


def test_production_guard_skipped_outside_production():
    from app.config import assert_production_security

    # Every value insecure, but development → guard is a no-op.
    assert (
        assert_production_security(
            _cfg(
                app_env="development",
                auth_secret="change-me-auth",
                refresh_secret="change-me-refresh",
                qr_secret="change-me-qr",
                bootstrap_admin_password="ChangeThisAdminPassword123!",
            )
        )
        is None
    )


# --------------------------------------------------------------------------- #
# 2. Login brute-force lockout
# --------------------------------------------------------------------------- #
def _bad_login(client, email="director.a@test.com"):
    return client.post(
        "/api/auth/login",
        json={"email": email, "password": "WrongPassword!", "device_fingerprint": "attacker-fp-xx"},
    )


def test_login_locks_out_after_repeated_failures(client, seeded):
    from app.config import settings

    # First N failures are plain 401s.
    for _ in range(settings.login_max_failures):
        assert _bad_login(client).status_code == 401

    # The next attempt is throttled even though the credentials are just wrong.
    assert _bad_login(client).status_code == 429

    # A locked account can't get in even with the CORRECT password.
    r = client.post(
        "/api/auth/login",
        json={"email": "director.a@test.com", "password": "DirPassword123!", "device_fingerprint": "real-fp-yy"},
    )
    assert r.status_code == 429


def test_lockout_is_scoped_per_account(client, seeded):
    from app.config import settings

    # Hammer director.a into a lockout.
    for _ in range(settings.login_max_failures + 1):
        _bad_login(client, "director.a@test.com")
    assert _bad_login(client, "director.a@test.com").status_code == 429

    # A different account on the same client is unaffected and logs in fine.
    r = client.post(
        "/api/auth/login",
        json={"email": "director.b@test.com", "password": "DirPassword123!", "device_fingerprint": "dirb-fp-zz"},
    )
    assert r.status_code == 200


def test_successful_login_resets_failure_counter(client, seeded):
    from app.config import settings

    # A few failures, then a success, then a few more failures must NOT lock:
    # the success cleared the counter.
    for _ in range(settings.login_max_failures - 1):
        assert _bad_login(client).status_code == 401

    r = client.post(
        "/api/auth/login",
        json={"email": "director.a@test.com", "password": "DirPassword123!", "device_fingerprint": "good-fp-11"},
    )
    assert r.status_code == 200

    for _ in range(settings.login_max_failures - 1):
        assert _bad_login(client).status_code == 401  # still under threshold


# --------------------------------------------------------------------------- #
# 3. QR campus binding
# --------------------------------------------------------------------------- #
def _qr_token(client, campus_id=None):
    url = "/api/qr/token"
    if campus_id is not None:
        url += f"?campus_id={campus_id}"
    return client.get(url).json()["token"]


def test_scan_with_matching_campus_token_succeeds(client, seeded):
    token = _qr_token(client, seeded["campus_a"]["id"])  # staff is at campus A
    r = client.post("/api/scan", headers=seeded["staff_headers"], json={"qr_token": token})
    assert r.status_code == 200


def test_scan_with_other_campus_token_rejected(client, seeded):
    token = _qr_token(client, seeded["campus_b"]["id"])  # wrong campus
    r = client.post("/api/scan", headers=seeded["staff_headers"], json={"qr_token": token})
    assert r.status_code == 403
    assert "kampüs" in r.json()["detail"].lower()


def test_scan_with_unbound_token_still_succeeds(client, seeded):
    # Backward compatibility: a token minted without a campus id (older kiosk)
    # is still accepted.
    token = _qr_token(client)
    r = client.post("/api/scan", headers=seeded["staff_headers"], json={"qr_token": token})
    assert r.status_code == 200


# --------------------------------------------------------------------------- #
# Campus geofence (location verification): a scan must come from within the
# campus radius; far-away attempts are rejected and reported.
# --------------------------------------------------------------------------- #
def _set_geofence(client, seeded, campus, lat, lng, radius=500):
    r = client.patch(
        f"/api/campuses/{campus['id']}/location",
        headers=seeded["hq_headers"],
        json={"latitude": lat, "longitude": lng, "geofence_radius_m": radius},
    )
    assert r.status_code == 200, r.text


def test_scan_within_geofence_succeeds(client, seeded):
    _set_geofence(client, seeded, seeded["campus_a"], 41.0, 29.0)
    token = _qr_token(client, seeded["campus_a"]["id"])
    r = client.post(
        "/api/scan",
        headers=seeded["staff_headers"],
        json={"qr_token": token, "latitude": 41.0, "longitude": 29.0, "accuracy": 12},
    )
    assert r.status_code == 200


def test_scan_outside_geofence_rejected_and_reported(client, seeded):
    _set_geofence(client, seeded, seeded["campus_a"], 41.0, 29.0, radius=500)
    token = _qr_token(client, seeded["campus_a"]["id"])
    # ~11 km north of the campus.
    r = client.post(
        "/api/scan",
        headers=seeded["staff_headers"],
        json={"qr_token": token, "latitude": 41.1, "longitude": 29.0, "accuracy": 12},
    )
    assert r.status_code == 403
    assert "konum" in r.json()["detail"].lower()

    # The attempt is surfaced to the campus director.
    alerts = client.get(
        "/api/reports/location-alerts", headers=seeded["dir_a_headers"]
    ).json()
    assert alerts["count"] == 1
    entry = alerts["entries"][0]
    assert entry["user_id"] == seeded["staff_id"]
    assert entry["distance_m"] > 500


def test_scan_without_location_blocked_when_geofenced(client, seeded):
    _set_geofence(client, seeded, seeded["campus_a"], 41.0, 29.0)
    token = _qr_token(client, seeded["campus_a"]["id"])
    r = client.post(
        "/api/scan", headers=seeded["staff_headers"], json={"qr_token": token}
    )
    assert r.status_code == 400
    assert "konum" in r.json()["detail"].lower()


def test_geofence_pause_and_resume_keeps_coordinates(client, seeded):
    campus = seeded["campus_a"]
    _set_geofence(client, seeded, campus, 41.0, 29.0)

    # Active → a scan without location is blocked.
    token = _qr_token(client, campus["id"])
    r = client.post("/api/scan", headers=seeded["staff_headers"], json={"qr_token": token})
    assert r.status_code == 400

    # Pause from the panel — coordinates are preserved.
    r = client.patch(
        f"/api/campuses/{campus['id']}/geofence-enabled",
        headers=seeded["hq_headers"],
        params={"enabled": "false"},
    )
    assert r.status_code == 200
    assert r.json()["geofence_enabled"] is False
    assert r.json()["latitude"] == 41.0

    # Paused → a scan without location now succeeds.
    token = _qr_token(client, campus["id"])
    r = client.post("/api/scan", headers=seeded["staff_headers"], json={"qr_token": token})
    assert r.status_code == 200

    # Resume → location required again (coordinates were kept).
    r = client.patch(
        f"/api/campuses/{campus['id']}/geofence-enabled",
        headers=seeded["hq_headers"],
        params={"enabled": "true"},
    )
    assert r.json()["geofence_enabled"] is True
    token = _qr_token(client, campus["id"])
    r = client.post("/api/scan", headers=seeded["staff_headers"], json={"qr_token": token})
    assert r.status_code == 400


def test_geofence_enable_toggle_is_hq_only(client, seeded):
    r = client.patch(
        f"/api/campuses/{seeded['campus_a']['id']}/geofence-enabled",
        headers=seeded["dir_a_headers"],
        params={"enabled": "false"},
    )
    assert r.status_code == 403


def test_scan_without_geofence_ignores_location(client, seeded):
    # No coordinates configured → location is optional and the scan succeeds.
    token = _qr_token(client, seeded["campus_a"]["id"])
    r = client.post(
        "/api/scan", headers=seeded["staff_headers"], json={"qr_token": token}
    )
    assert r.status_code == 200


def test_geofence_requires_both_coordinates(client, seeded):
    r = client.patch(
        f"/api/campuses/{seeded['campus_a']['id']}/location",
        headers=seeded["hq_headers"],
        json={"latitude": 41.0, "longitude": None, "geofence_radius_m": 500},
    )
    assert r.status_code == 400


def test_geofence_location_update_is_hq_only(client, seeded):
    r = client.patch(
        f"/api/campuses/{seeded['campus_a']['id']}/location",
        headers=seeded["dir_a_headers"],
        json={"latitude": 41.0, "longitude": 29.0, "geofence_radius_m": 500},
    )
    assert r.status_code == 403
