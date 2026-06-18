"""Integration tests for the second batch of workflows:

  1. Bulk staff import (start-of-year roster) + self-register re-claim.
  2. Daily attendance trend aggregates (chart data).
  3. "Forgot to check out" reminders (manager list + staff self-status).
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def _today_local():
    return datetime.now(timezone.utc).astimezone(ZoneInfo("Europe/Istanbul")).date()


# --------------------------------------------------------------------------- #
# 1. Bulk staff import
# --------------------------------------------------------------------------- #
def test_bulk_import_creates_active_staff(client, seeded):
    r = client.post(
        "/api/staff/bulk",
        headers=seeded["dir_a_headers"],
        json={
            "rows": [
                {"full_name": "Ali Veli", "phone": "0533 100 00 01", "job_title": "Öğretmen", "branch": "Fizik"},
                {"full_name": "Veli Can", "phone": "0533 100 00 02", "job_title": "Öğretmen", "branch": "Kimya"},
            ]
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["created_count"] == 2
    assert body["skipped_count"] == 0

    staff = client.get("/api/staff", headers=seeded["dir_a_headers"]).json()
    imported = {u["full_name"]: u for u in staff if u["full_name"] in ("Ali Veli", "Veli Can")}
    assert len(imported) == 2
    for u in imported.values():
        assert u["status"] == "active"
        assert u["has_device"] is False
        assert u["campus_id"] == seeded["campus_a"]["id"]


def test_bulk_import_skips_duplicates(client, seeded):
    payload = {
        "rows": [
            {"full_name": "Tekrar Bir", "phone": "0533 222 00 01", "job_title": "Öğretmen", "branch": "Tarih"},
            # Same phone twice inside the file → second is skipped.
            {"full_name": "Tekrar Bir Kopya", "phone": "0533 222 00 01", "job_title": "Öğretmen", "branch": "Tarih"},
        ]
    }
    r = client.post("/api/staff/bulk", headers=seeded["dir_a_headers"], json=payload)
    body = r.json()
    assert body["created_count"] == 1
    assert body["skipped_count"] == 1

    # Re-uploading the file is idempotent: both rows now collide with the
    # account created on the first run.
    r2 = client.post("/api/staff/bulk", headers=seeded["dir_a_headers"], json=payload)
    assert r2.json()["created_count"] == 0
    assert r2.json()["skipped_count"] == 2


def test_bulk_import_then_self_register_binds_device(client, seeded):
    phone = "0533 333 00 09"
    client.post(
        "/api/staff/bulk",
        headers=seeded["dir_a_headers"],
        json={"rows": [{"full_name": "Zeynep Ak", "phone": phone, "job_title": "Öğretmen", "branch": "Müzik"}]},
    )
    # The staff member binds a device by self-registering with the SAME phone.
    r = client.post(
        "/api/auth/register",
        json={
            "full_name": "Zeynep Ak",
            "phone": phone,
            "job_title": "Öğretmen",
            "branch": "Müzik",
            "birth_date": "1992-03-03",
            "tc_kimlik_no": "44444444068",
            "campus_id": seeded["campus_a"]["id"],
            "device_fingerprint": "zeynep-fp-12345678",
        },
    )
    assert r.status_code == 201
    user = r.json()["user"]
    # Re-claim keeps the imported (already active) account and now has a device.
    assert user["status"] == "active"
    assert user["has_device"] is True


def test_bulk_import_hq_requires_campus(client, seeded):
    # hq with no campus on the row and no request-level default → skipped.
    r = client.post(
        "/api/staff/bulk",
        headers=seeded["hq_headers"],
        json={"rows": [{"full_name": "Kampüssüz", "phone": "0534 000 00 01", "job_title": "Öğretmen", "branch": "X"}]},
    )
    assert r.json()["created_count"] == 0
    assert "Kampüs" in r.json()["results"][0]["reason"]

    # With a per-row campus it succeeds.
    r2 = client.post(
        "/api/staff/bulk",
        headers=seeded["hq_headers"],
        json={
            "rows": [
                {
                    "full_name": "Kampüslü",
                    "phone": "0534 000 00 02",
                    "job_title": "Öğretmen",
                    "branch": "X",
                    "campus_id": seeded["campus_b"]["id"],
                }
            ]
        },
    )
    assert r2.json()["created_count"] == 1


# --------------------------------------------------------------------------- #
# 2. Daily attendance trend
# --------------------------------------------------------------------------- #
def test_daily_trend_counts(client, seeded):
    today = _today_local()
    d_present = today - timedelta(days=5)
    d_leave = today - timedelta(days=4)
    # d_unresolved = today - 3 (no activity)
    start = today - timedelta(days=5)
    end = today - timedelta(days=3)

    # Present on d_present (a manual IN is enough to count the day as present).
    r = client.post(
        "/api/logs/manual",
        headers=seeded["dir_a_headers"],
        json={
            "user_id": seeded["staff_id"],
            "type": "IN",
            "date": d_present.isoformat(),
            "time": "12:00:00",
        },
    )
    assert r.status_code == 201

    # On leave on d_leave.
    client.post(
        "/api/leaves",
        headers=seeded["dir_a_headers"],
        json={
            "user_id": seeded["staff_id"],
            "leave_type": "Ücretli izin",
            "start_date": d_leave.isoformat(),
            "end_date": d_leave.isoformat(),
        },
    )

    r = client.get(
        "/api/reports/daily-trend",
        headers=seeded["dir_a_headers"],
        params={"start_date": start.isoformat(), "end_date": end.isoformat(), "exclude_weekends": False},
    )
    assert r.status_code == 200
    body = r.json()
    # One staff member, three expected days, one of each outcome.
    assert body["total_expected"] == 3
    assert body["total_present"] == 1
    assert body["total_on_leave"] == 1
    assert body["total_unresolved"] == 1
    assert len(body["entries"]) == 3


# --------------------------------------------------------------------------- #
# 3. Forgot-to-check-out reminders
# --------------------------------------------------------------------------- #
def _set_shift(client, seeded, campus, start="00:01:00", end="00:01:00"):
    client.patch(
        f"/api/campuses/{campus['id']}/shift",
        headers=seeded["hq_headers"],
        json={"shift_start": start, "shift_end": end},
    )


def test_forgot_checkout_lists_overdue(client, seeded):
    today = _today_local()
    # Campus A shift ends at 00:01 — already long past by test time.
    _set_shift(client, seeded, seeded["campus_a"])

    # Staff has an open IN today and no OUT → still "inside".
    r = client.post(
        "/api/logs/manual",
        headers=seeded["dir_a_headers"],
        json={
            "user_id": seeded["staff_id"],
            "type": "IN",
            "date": today.isoformat(),
            "time": "00:05:00",
        },
    )
    assert r.status_code == 201

    # threshold_minutes=0 so the assertion does not depend on the wall-clock
    # being more than the default grace into the day.
    r = client.get(
        "/api/reports/forgot-checkout",
        headers=seeded["dir_a_headers"],
        params={"threshold_minutes": 0},
    )
    assert r.status_code == 200
    entries = r.json()["entries"]
    assert any(e["user_id"] == seeded["staff_id"] and e["minutes_overdue"] >= 0 for e in entries)


def test_forgot_checkout_excludes_when_no_open_in(client, seeded):
    _set_shift(client, seeded, seeded["campus_a"])
    # No scan today at all → not "inside" → not in the list.
    r = client.get("/api/reports/forgot-checkout", headers=seeded["dir_a_headers"])
    assert all(e["user_id"] != seeded["staff_id"] for e in r.json()["entries"])


def test_my_status_should_check_out(client, seeded):
    today = _today_local()
    _set_shift(client, seeded, seeded["campus_a"])
    client.post(
        "/api/logs/manual",
        headers=seeded["dir_a_headers"],
        json={
            "user_id": seeded["staff_id"],
            "type": "IN",
            "date": today.isoformat(),
            "time": "00:05:00",
        },
    )
    r = client.get("/api/logs/me/status", headers=seeded["staff_headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["currently_in"] is True
    assert body["should_check_out"] is True
    assert body["minutes_overdue"] > 0
