"""Integration tests for manual attendance entry, leave/absence management,
hq-only shift hours, and the late/early-leave/absence reporting endpoints.

Historical test data uses fixed 2026-06 dates safely in the past relative to
the suite's run date; leave ranges that must cover "today" are computed from
the system clock (in the same timezone the app uses) so they stay correct no
matter when the suite runs.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def _today_local():
    return datetime.now(timezone.utc).astimezone(ZoneInfo("Europe/Istanbul")).date()


# --------------------------------------------------------------------------- #
# Manual attendance entry
# --------------------------------------------------------------------------- #
def test_manual_entry_creates_in_then_out(client, seeded):
    r = client.post(
        "/api/logs/manual",
        headers=seeded["dir_a_headers"],
        json={"user_id": seeded["staff_id"], "type": "IN", "date": "2026-06-10", "time": "08:10:00", "note": "Telefon arızalı"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["source"] == "director_manual"
    assert body["recorded_by_name"] == "Müdür A"

    r = client.post(
        "/api/logs/manual",
        headers=seeded["dir_a_headers"],
        json={"user_id": seeded["staff_id"], "type": "OUT", "date": "2026-06-10", "time": "17:05:00"},
    )
    assert r.status_code == 201
    assert r.json()["source"] == "director_manual"


def test_manual_entry_duplicate_in_rejected(client, seeded):
    payload = {"user_id": seeded["staff_id"], "type": "IN", "date": "2026-06-10", "time": "08:10:00"}
    r = client.post("/api/logs/manual", headers=seeded["dir_a_headers"], json=payload)
    assert r.status_code == 201

    r = client.post(
        "/api/logs/manual",
        headers=seeded["dir_a_headers"],
        json={**payload, "time": "08:20:00"},
    )
    assert r.status_code == 409


def test_manual_entry_future_date_rejected(client, seeded):
    r = client.post(
        "/api/logs/manual",
        headers=seeded["dir_a_headers"],
        json={"user_id": seeded["staff_id"], "type": "IN", "date": "2099-01-01", "time": "08:00:00"},
    )
    assert r.status_code == 400


def test_manual_entry_cross_campus_rejected(client, seeded):
    r = client.post(
        "/api/logs/manual",
        headers=seeded["dir_b_headers"],
        json={"user_id": seeded["staff_id"], "type": "IN", "date": "2026-06-11", "time": "08:00:00"},
    )
    assert r.status_code == 403


def test_manual_entry_blocked_during_active_leave(client, seeded):
    r = client.post(
        "/api/leaves",
        headers=seeded["dir_a_headers"],
        json={"user_id": seeded["staff_id"], "leave_type": "Sağlık raporu", "start_date": "2026-06-10", "end_date": "2026-06-12"},
    )
    assert r.status_code == 201

    r = client.post(
        "/api/logs/manual",
        headers=seeded["dir_a_headers"],
        json={"user_id": seeded["staff_id"], "type": "IN", "date": "2026-06-11", "time": "08:00:00"},
    )
    assert r.status_code == 409
    assert "Sağlık raporu" in r.json()["detail"]


# --------------------------------------------------------------------------- #
# Leave / absence records
# --------------------------------------------------------------------------- #
def test_leave_types_suggestions(client, seeded):
    r = client.get("/api/leaves/types", headers=seeded["dir_a_headers"])
    assert r.status_code == 200
    assert "Sağlık raporu" in r.json()["suggested"]


def test_leave_create_list_patch_cancel(client, seeded):
    r = client.post(
        "/api/leaves",
        headers=seeded["dir_a_headers"],
        json={"user_id": seeded["staff_id"], "leave_type": "Ücretli izin", "start_date": "2026-07-01", "end_date": "2026-07-05", "note": "Yıllık izin"},
    )
    assert r.status_code == 201
    leave = r.json()
    assert leave["status"] == "active"

    r = client.get("/api/leaves", headers=seeded["dir_a_headers"], params={"user_id": seeded["staff_id"]})
    assert r.status_code == 200
    assert any(row["id"] == leave["id"] for row in r.json())

    # staff member actually showed up partway through — shorten the range.
    r = client.patch(
        f"/api/leaves/{leave['id']}", headers=seeded["dir_a_headers"], json={"end_date": "2026-07-03"}
    )
    assert r.status_code == 200
    assert r.json()["end_date"] == "2026-07-03"

    r = client.post(f"/api/leaves/{leave['id']}/cancel", headers=seeded["dir_a_headers"])
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"


def test_leave_cross_campus_rejected(client, seeded):
    r = client.post(
        "/api/leaves",
        headers=seeded["dir_b_headers"],
        json={"user_id": seeded["staff_id"], "leave_type": "Ücretli izin", "start_date": "2026-07-01", "end_date": "2026-07-02"},
    )
    assert r.status_code == 403


def test_leave_invalid_range_rejected(client, seeded):
    r = client.post(
        "/api/leaves",
        headers=seeded["dir_a_headers"],
        json={"user_id": seeded["staff_id"], "leave_type": "Ücretli izin", "start_date": "2026-07-05", "end_date": "2026-07-01"},
    )
    assert r.status_code == 422


def test_scan_blocked_during_active_leave_and_unblocked_after_cancel(client, seeded):
    today = _today_local()
    r = client.post(
        "/api/leaves",
        headers=seeded["dir_a_headers"],
        json={
            "user_id": seeded["staff_id"],
            "leave_type": "Sağlık raporu",
            "start_date": (today - timedelta(days=1)).isoformat(),
            "end_date": (today + timedelta(days=2)).isoformat(),
        },
    )
    assert r.status_code == 201
    leave_id = r.json()["id"]

    qr_token = client.get("/api/qr/token").json()["token"]
    r = client.post("/api/scan", headers=seeded["staff_headers"], json={"qr_token": qr_token})
    assert r.status_code == 409
    assert "Sağlık raporu" in r.json()["detail"]

    r = client.post(f"/api/leaves/{leave_id}/cancel", headers=seeded["dir_a_headers"])
    assert r.status_code == 200

    qr_token = client.get("/api/qr/token").json()["token"]
    r = client.post("/api/scan", headers=seeded["staff_headers"], json={"qr_token": qr_token})
    assert r.status_code == 200


# --------------------------------------------------------------------------- #
# Shift hours — hq-only
# --------------------------------------------------------------------------- #
def test_hq_set_shift_hours_visible_via_campus_list(client, seeded):
    r = client.get("/api/campuses")
    campus_a = next(c for c in r.json() if c["id"] == seeded["campus_a"]["id"])
    assert campus_a["shift_start"] == "08:00:00"
    assert campus_a["shift_end"] == "17:00:00"


def test_director_cannot_set_shift_hours(client, seeded):
    r = client.patch(
        f"/api/campuses/{seeded['campus_a']['id']}/shift",
        headers=seeded["dir_a_headers"],
        json={"shift_start": "09:00:00", "shift_end": "18:00:00"},
    )
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #
def test_late_ranking_flags_late_arrival(client, seeded):
    r = client.post(
        "/api/logs/manual",
        headers=seeded["dir_a_headers"],
        json={"user_id": seeded["staff_id"], "type": "IN", "date": "2026-06-10", "time": "08:10:00"},
    )
    assert r.status_code == 201

    r = client.get(
        "/api/reports/late",
        headers=seeded["dir_a_headers"],
        params={"start_date": "2026-06-01", "end_date": "2026-06-30", "threshold_minutes": 0},
    )
    assert r.status_code == 200
    assert any(row["user_id"] == seeded["staff_id"] for row in r.json())


def test_early_leave_ranking_flags_early_departure(client, seeded):
    r = client.post(
        "/api/logs/manual",
        headers=seeded["dir_a_headers"],
        json={"user_id": seeded["staff_id"], "type": "IN", "date": "2026-06-11", "time": "08:00:00"},
    )
    assert r.status_code == 201
    r = client.post(
        "/api/logs/manual",
        headers=seeded["dir_a_headers"],
        json={"user_id": seeded["staff_id"], "type": "OUT", "date": "2026-06-11", "time": "16:30:00"},
    )
    assert r.status_code == 201

    r = client.get(
        "/api/reports/early-leave",
        headers=seeded["dir_a_headers"],
        params={"start_date": "2026-06-01", "end_date": "2026-06-30", "threshold_minutes": 0},
    )
    assert r.status_code == 200
    assert any(row["user_id"] == seeded["staff_id"] for row in r.json())


def test_absence_detail_flags_unresolved_when_no_leave_covers(client, seeded):
    r = client.get(
        "/api/reports/absences",
        headers=seeded["dir_a_headers"],
        params={"start_date": "2026-06-08", "end_date": "2026-06-09", "exclude_weekends": "false"},
    )
    assert r.status_code == 200
    rows = r.json()
    assert rows
    assert all(row["status"] == "unresolved" for row in rows)


def test_absence_summary_counts_unresolved(client, seeded):
    r = client.get(
        "/api/reports/absence-summary",
        headers=seeded["dir_a_headers"],
        params={"start_date": "2026-06-01", "end_date": "2026-06-30", "exclude_weekends": "false"},
    )
    assert r.status_code == 200
    assert r.json()["unresolved_count"] > 0


# --------------------------------------------------------------------------- #
# Exports
# --------------------------------------------------------------------------- #
def test_logs_range_filter_includes_both_sources(client, seeded):
    qr_token = client.get("/api/qr/token").json()["token"]
    r = client.post("/api/scan", headers=seeded["staff_headers"], json={"qr_token": qr_token})
    assert r.status_code == 200

    r = client.post(
        "/api/logs/manual",
        headers=seeded["dir_a_headers"],
        json={"user_id": seeded["staff_id"], "type": "IN", "date": "2026-06-10", "time": "08:00:00"},
    )
    assert r.status_code == 201

    r = client.get(
        "/api/logs",
        headers=seeded["dir_a_headers"],
        params={"start_date": "2026-06-01", "end_date": "2026-06-30"},
    )
    assert r.status_code == 200
    sources = {row["source"] for row in r.json()}
    assert sources == {"qr_scan", "director_manual"}


def test_logs_xlsx_export(client, seeded):
    r = client.get("/api/logs/export.xlsx", headers=seeded["dir_a_headers"])
    assert r.status_code == 200
    assert len(r.content) > 0


def test_reports_xlsx_export(client, seeded):
    r = client.get(
        "/api/reports/export.xlsx",
        headers=seeded["dir_a_headers"],
        params={"start_date": "2026-06-01", "end_date": "2026-06-30"},
    )
    assert r.status_code == 200
    assert len(r.content) > 0
