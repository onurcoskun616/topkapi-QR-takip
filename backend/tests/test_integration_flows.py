"""Integration tests for manual attendance entry, leave/absence management,
hq-only shift hours, and the late/early-leave/absence reporting endpoints.

Historical test data uses fixed 2026-06 dates safely in the past relative to
the suite's run date; leave ranges that must cover "today" are computed from
the system clock (in the same timezone the app uses) so they stay correct no
matter when the suite runs.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from conftest import backdate_users_created_at, set_user_created_at


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
# QR token status — lets a kiosk notice its own code was scanned and roll
# over immediately, instead of waiting out the rest of its 15s window. Each
# kiosk always mints its own independently-random code (different jti every
# time), so the same code can never appear on two tablets at once.
# --------------------------------------------------------------------------- #
def test_qr_token_status_flips_to_used_after_scan(client, seeded):
    issued = client.get("/api/qr/token").json()
    assert issued["jti"]

    r = client.get(f"/api/qr/token/{issued['jti']}/status")
    assert r.status_code == 200
    assert r.json() == {"used": False}

    r = client.post(
        "/api/scan", headers=seeded["staff_headers"], json={"qr_token": issued["token"]}
    )
    assert r.status_code == 200

    r = client.get(f"/api/qr/token/{issued['jti']}/status")
    assert r.json() == {"used": True}


def test_qr_token_status_unknown_jti_is_unused(client, seeded):
    r = client.get("/api/qr/token/never-issued-jti/status")
    assert r.status_code == 200
    assert r.json() == {"used": False}


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
# Directors — hq can disable, re-enable, and reset a director's password
# --------------------------------------------------------------------------- #
def _director_id(client, hq_headers, email):
    directors = client.get("/api/directors", headers=hq_headers).json()
    return next(d for d in directors if d["email"] == email)["id"]


def test_hq_can_reenable_disabled_director(client, seeded):
    hq_headers = seeded["hq_headers"]
    director_id = _director_id(client, hq_headers, "director.a@test.com")

    r = client.post(f"/api/directors/{director_id}/disable", headers=hq_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "disabled"

    r = client.post(f"/api/directors/{director_id}/enable", headers=hq_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "active"

    r = client.post(
        "/api/auth/login",
        json={"email": "director.a@test.com", "password": "DirPassword123!", "device_fingerprint": "dir-a-fp-cccc"},
    )
    assert r.status_code == 200


def test_director_cannot_reenable_director(client, seeded):
    director_id = _director_id(client, seeded["hq_headers"], "director.b@test.com")
    r = client.post(f"/api/directors/{director_id}/enable", headers=seeded["dir_a_headers"])
    assert r.status_code == 403


def test_hq_can_reset_director_password(client, seeded):
    hq_headers = seeded["hq_headers"]
    director_id = _director_id(client, hq_headers, "director.a@test.com")

    r = client.post(
        f"/api/directors/{director_id}/password",
        headers=hq_headers,
        json={"password": "NewDirPassword456!"},
    )
    assert r.status_code == 200

    # Old password no longer works; new one logs in fine.
    r = client.post(
        "/api/auth/login",
        json={"email": "director.a@test.com", "password": "DirPassword123!", "device_fingerprint": "dir-a-fp-dddd"},
    )
    assert r.status_code == 401

    r = client.post(
        "/api/auth/login",
        json={"email": "director.a@test.com", "password": "NewDirPassword456!", "device_fingerprint": "dir-a-fp-eeee"},
    )
    assert r.status_code == 200


def test_director_cannot_reset_director_password(client, seeded):
    director_id = _director_id(client, seeded["hq_headers"], "director.b@test.com")
    r = client.post(
        f"/api/directors/{director_id}/password",
        headers=seeded["dir_a_headers"],
        json={"password": "NewDirPassword456!"},
    )
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# Self-service password change — any logged-in manager (director or hq)
# --------------------------------------------------------------------------- #
def test_manager_can_change_own_password(client, seeded):
    r = client.post(
        "/api/auth/change-password",
        headers=seeded["dir_a_headers"],
        json={"current_password": "DirPassword123!", "new_password": "SelfChanged789!"},
    )
    assert r.status_code == 204

    r = client.post(
        "/api/auth/login",
        json={"email": "director.a@test.com", "password": "DirPassword123!", "device_fingerprint": "dir-a-fp-ffff"},
    )
    assert r.status_code == 401

    r = client.post(
        "/api/auth/login",
        json={"email": "director.a@test.com", "password": "SelfChanged789!", "device_fingerprint": "dir-a-fp-gggg"},
    )
    assert r.status_code == 200


def test_change_password_rejects_wrong_current_password(client, seeded):
    r = client.post(
        "/api/auth/change-password",
        headers=seeded["dir_a_headers"],
        json={"current_password": "WrongPassword!", "new_password": "SelfChanged789!"},
    )
    assert r.status_code == 400


def test_staff_cannot_change_password(client, seeded):
    r = client.post(
        "/api/auth/change-password",
        headers=seeded["staff_headers"],
        json={"current_password": "anything", "new_password": "SelfChanged789!"},
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


def test_late_detail_lists_each_event_with_date_and_time(client, seeded):
    for day, t in (("2026-06-10", "08:25:00"), ("2026-06-09", "08:05:00")):
        r = client.post(
            "/api/logs/manual",
            headers=seeded["dir_a_headers"],
            json={"user_id": seeded["staff_id"], "type": "IN", "date": day, "time": t},
        )
        assert r.status_code == 201

    r = client.get(
        "/api/reports/late-detail",
        headers=seeded["dir_a_headers"],
        params={"start_date": "2026-06-01", "end_date": "2026-06-30", "threshold_minutes": 0},
    )
    assert r.status_code == 200
    rows = r.json()
    mine = [row for row in rows if row["user_id"] == seeded["staff_id"]]
    assert len(mine) == 2
    # Sorted chronologically by (date, time): the 09th comes before the 10th.
    assert mine[0]["date"] == "2026-06-09" and mine[0]["arrival_time"] == "08:05"
    assert mine[1]["date"] == "2026-06-10" and mine[1]["arrival_time"] == "08:25"
    assert mine[1]["minutes_late"] == 25
    assert mine[1]["shift_start"] == "08:00"
    # Reports carry the person's görev (job_title) and branş (branch).
    assert mine[0]["job_title"] == "Öğretmen"
    assert mine[0]["branch"] == "Matematik"


def test_late_ranking_includes_job_title_and_branch(client, seeded):
    r = client.post(
        "/api/logs/manual",
        headers=seeded["dir_a_headers"],
        json={"user_id": seeded["staff_id"], "type": "IN", "date": "2026-06-09", "time": "08:40:00"},
    )
    assert r.status_code == 201

    r = client.get(
        "/api/reports/late",
        headers=seeded["dir_a_headers"],
        params={"start_date": "2026-06-01", "end_date": "2026-06-30", "threshold_minutes": 0},
    )
    assert r.status_code == 200
    mine = [row for row in r.json() if row["user_id"] == seeded["staff_id"]]
    assert len(mine) == 1
    assert mine[0]["job_title"] == "Öğretmen"
    assert mine[0]["branch"] == "Matematik"


def test_early_leave_detail_lists_each_event_with_date_and_time(client, seeded):
    r = client.post(
        "/api/logs/manual",
        headers=seeded["dir_a_headers"],
        json={"user_id": seeded["staff_id"], "type": "IN", "date": "2026-06-12", "time": "08:00:00"},
    )
    assert r.status_code == 201
    r = client.post(
        "/api/logs/manual",
        headers=seeded["dir_a_headers"],
        json={"user_id": seeded["staff_id"], "type": "OUT", "date": "2026-06-12", "time": "16:20:00"},
    )
    assert r.status_code == 201

    r = client.get(
        "/api/reports/early-leave-detail",
        headers=seeded["dir_a_headers"],
        params={"start_date": "2026-06-01", "end_date": "2026-06-30", "threshold_minutes": 0},
    )
    assert r.status_code == 200
    mine = [row for row in r.json() if row["user_id"] == seeded["staff_id"]]
    assert len(mine) == 1
    assert mine[0]["date"] == "2026-06-12"
    assert mine[0]["leave_time"] == "16:20"
    assert mine[0]["shift_end"] == "17:00"
    assert mine[0]["minutes_early"] == 40


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


def test_absence_not_counted_before_registration_date(client, seeded):
    """Go-live rule: a staff member is never absent for days before their
    registration (account-creation) date — only from that day onward."""
    # Pretend this person registered mid-June.
    set_user_created_at(seeded["staff_id"], "2026-06-15 00:00:00")

    # A range entirely BEFORE the registration date → nothing is expected, so no
    # unresolved absences.
    before = client.get(
        "/api/reports/absence-summary",
        headers=seeded["dir_a_headers"],
        params={"start_date": "2026-06-01", "end_date": "2026-06-12", "exclude_weekends": "false"},
    ).json()
    assert before["unresolved_count"] == 0

    # A range AFTER registration with no scans → those days ARE unresolved.
    after = client.get(
        "/api/reports/absence-summary",
        headers=seeded["dir_a_headers"],
        params={"start_date": "2026-06-16", "end_date": "2026-06-20", "exclude_weekends": "false"},
    ).json()
    assert after["unresolved_count"] > 0


def test_absence_summary_counts_unresolved(client, seeded):
    r = client.get(
        "/api/reports/absence-summary",
        headers=seeded["dir_a_headers"],
        params={"start_date": "2026-06-01", "end_date": "2026-06-30", "exclude_weekends": "false"},
    )
    assert r.status_code == 200
    assert r.json()["unresolved_count"] > 0


# --------------------------------------------------------------------------- #
# Risk / early-warning panel (threshold layer over the reports)
# --------------------------------------------------------------------------- #
def test_risk_flags_repeated_late_arrivals(client, seeded):
    # Four weekdays in the past, each a 30-min-late IN (and a scan, so the day
    # counts as present — no unresolved absence in this tight range).
    for d in ("2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04"):
        r = client.post(
            "/api/logs/manual",
            headers=seeded["dir_a_headers"],
            json={"user_id": seeded["staff_id"], "type": "IN", "date": d, "time": "08:30:00"},
        )
        assert r.status_code == 201

    params = {
        "start_date": "2026-06-01",
        "end_date": "2026-06-04",
        "threshold_minutes": 0,
        "late_threshold": 3,
        "early_leave_threshold": 3,
        "unresolved_threshold": 2,
    }
    r = client.get("/api/reports/risk", headers=seeded["dir_a_headers"], params=params)
    assert r.status_code == 200
    body = r.json()
    mine = [e for e in body["entries"] if e["user_id"] == seeded["staff_id"]]
    assert len(mine) == 1
    assert mine[0]["late_days"] == 4
    assert mine[0]["unresolved_days"] == 0
    assert mine[0]["level"] in ("medium", "high")
    assert any("geç" in f.lower() for f in mine[0]["flags"])

    # Raising the bar above the actual count clears the flag.
    r = client.get(
        "/api/reports/risk",
        headers=seeded["dir_a_headers"],
        params={**params, "late_threshold": 10},
    )
    assert all(e["user_id"] != seeded["staff_id"] for e in r.json()["entries"])


def test_risk_flags_unresolved_absences_as_high(client, seeded):
    # No scans across this past range → unresolved absences pile up → high risk.
    params = {
        "start_date": "2026-06-01",
        "end_date": "2026-06-10",
        "exclude_weekends": "false",
        "late_threshold": 50,
        "early_leave_threshold": 50,
        "unresolved_threshold": 2,
    }
    r = client.get("/api/reports/risk", headers=seeded["dir_a_headers"], params=params)
    assert r.status_code == 200
    body = r.json()
    mine = [e for e in body["entries"] if e["user_id"] == seeded["staff_id"]]
    assert len(mine) == 1
    assert mine[0]["unresolved_days"] >= 2
    assert mine[0]["level"] == "high"
    assert body["high_count"] >= 1


def test_risk_scoped_to_director_campus(client, seeded):
    # Campus B's director sees none of campus A's staff in the risk panel.
    for d in ("2026-06-01", "2026-06-02", "2026-06-03"):
        client.post(
            "/api/logs/manual",
            headers=seeded["dir_a_headers"],
            json={"user_id": seeded["staff_id"], "type": "IN", "date": d, "time": "08:40:00"},
        )
    r = client.get(
        "/api/reports/risk",
        headers=seeded["dir_b_headers"],
        params={"start_date": "2026-06-01", "end_date": "2026-06-03", "late_threshold": 1},
    )
    assert r.status_code == 200
    assert all(e["user_id"] != seeded["staff_id"] for e in r.json()["entries"])


# --------------------------------------------------------------------------- #
# Reports narrowed to a single person via user_id (per-person reporting)
# --------------------------------------------------------------------------- #
def test_today_absentees_lists_expected_then_drops_after_scan(client, seeded):
    # exclude_weekends=false so "today" is always a working day for the test,
    # regardless of which weekday the suite runs on.
    r = client.get(
        "/api/reports/today-absentees",
        headers=seeded["dir_a_headers"],
        params={"exclude_weekends": "false"},
    )
    assert r.status_code == 200
    body = r.json()
    assert seeded["staff_id"] in {e["user_id"] for e in body["entries"]}
    assert body["count"] >= 1

    # After a real scan today, the staff member is no longer "not here".
    qr_token = client.get("/api/qr/token").json()["token"]
    assert (
        client.post("/api/scan", headers=seeded["staff_headers"], json={"qr_token": qr_token}).status_code
        == 200
    )
    after = client.get(
        "/api/reports/today-absentees",
        headers=seeded["dir_a_headers"],
        params={"exclude_weekends": "false"},
    ).json()
    assert seeded["staff_id"] not in {e["user_id"] for e in after["entries"]}


def test_report_summary_buckets_move_after_scan(client, seeded):
    today = _today_local().isoformat()
    params = {"start_date": today, "end_date": today, "exclude_weekends": "false"}

    # Before anything: expected today, no scan, no leave → absent bucket.
    s1 = client.get("/api/reports/summary", headers=seeded["dir_a_headers"], params=params).json()
    assert s1["total_staff"] >= 1
    assert seeded["staff_id"] in {p["user_id"] for p in s1["absent"]}
    assert s1["on_time"] == [] and s1["late"] == []

    # A manual on-time IN (campus shift starts 08:00, so 07:30 is on time).
    r = client.post(
        "/api/logs/manual",
        headers=seeded["dir_a_headers"],
        json={"user_id": seeded["staff_id"], "type": "IN", "date": today, "time": "07:30:00"},
    )
    assert r.status_code == 201

    s2 = client.get("/api/reports/summary", headers=seeded["dir_a_headers"], params=params).json()
    assert seeded["staff_id"] in {p["user_id"] for p in s2["on_time"]}
    assert seeded["staff_id"] not in {p["user_id"] for p in s2["absent"]}


def _bulk_import_one(client, seeded, full_name, phone):
    r = client.post(
        "/api/staff/bulk",
        headers=seeded["dir_a_headers"],
        json={"rows": [{"full_name": full_name, "phone": phone, "job_title": "Öğretmen", "branch": "Tarih"}]},
    )
    assert r.status_code == 201
    staff = client.get("/api/staff", headers=seeded["dir_a_headers"]).json()
    # Backdate so the go-live tracking rule doesn't clip these tests' fixed past
    # report dates (the imported account is otherwise created "now").
    backdate_users_created_at()
    return next(u["id"] for u in staff if u["full_name"] == full_name)


def test_late_ranking_user_id_filters_to_one_person(client, seeded):
    other_id = _bulk_import_one(client, seeded, "Diğer Personel", "0533 555 44 33")

    for uid, t in ((seeded["staff_id"], "08:10:00"), (other_id, "08:20:00")):
        r = client.post(
            "/api/logs/manual",
            headers=seeded["dir_a_headers"],
            json={"user_id": uid, "type": "IN", "date": "2026-06-10", "time": t},
        )
        assert r.status_code == 201

    params = {"start_date": "2026-06-01", "end_date": "2026-06-30", "threshold_minutes": 0}
    r = client.get("/api/reports/late", headers=seeded["dir_a_headers"], params=params)
    assert {row["user_id"] for row in r.json()} == {seeded["staff_id"], other_id}

    r = client.get(
        "/api/reports/late", headers=seeded["dir_a_headers"], params={**params, "user_id": seeded["staff_id"]}
    )
    assert {row["user_id"] for row in r.json()} == {seeded["staff_id"]}


def test_daily_trend_user_id_narrows_to_one_person(client, seeded):
    other_id = _bulk_import_one(client, seeded, "Diğer Personel", "0533 555 44 33")
    d = _today_local() - timedelta(days=20)

    params = {"start_date": d.isoformat(), "end_date": d.isoformat(), "exclude_weekends": False}
    r = client.get("/api/reports/daily-trend", headers=seeded["dir_a_headers"], params=params)
    assert r.status_code == 200
    assert r.json()["total_expected"] == 2  # both staff expected that day

    r = client.get(
        "/api/reports/daily-trend",
        headers=seeded["dir_a_headers"],
        params={**params, "user_id": other_id},
    )
    assert r.status_code == 200
    assert r.json()["total_expected"] == 1


def test_absence_summary_user_id_narrows_to_one_person(client, seeded):
    other_id = _bulk_import_one(client, seeded, "Diğer Personel", "0533 555 44 33")

    params = {"start_date": "2026-06-08", "end_date": "2026-06-09", "exclude_weekends": "false"}
    r = client.get("/api/reports/absence-summary", headers=seeded["dir_a_headers"], params=params)
    both_unresolved = r.json()["unresolved_count"]

    r = client.get(
        "/api/reports/absence-summary",
        headers=seeded["dir_a_headers"],
        params={**params, "user_id": other_id},
    )
    assert r.json()["unresolved_count"] < both_unresolved


def test_export_xlsx_accepts_user_id_filter(client, seeded):
    other_id = _bulk_import_one(client, seeded, "Diğer Personel", "0533 555 44 33")
    r = client.get(
        "/api/reports/export.xlsx",
        headers=seeded["dir_a_headers"],
        params={"start_date": "2026-06-01", "end_date": "2026-06-30", "user_id": other_id},
    )
    assert r.status_code == 200
    assert len(r.content) > 0


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

    # The QR scan is stamped "today"; end the range at today so it's included
    # regardless of when the suite runs (the manual entry is the 2026-06-10 row).
    r = client.get(
        "/api/logs",
        headers=seeded["dir_a_headers"],
        params={"start_date": "2026-06-01", "end_date": _today_local().isoformat()},
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


# --------------------------------------------------------------------------- #
# Kiosk feed — green-check scan confirmation + birthday celebration
# --------------------------------------------------------------------------- #
def _set_birthday_today(client, seeded, headers=None):
    """Move the seeded staff member's birthday to today's month/day."""
    today = _today_local()
    headers = headers or seeded["dir_a_headers"]
    r = client.patch(
        f"/api/staff/{seeded['staff_id']}",
        headers=headers,
        json={"birth_date": today.replace(year=1990).isoformat()},
    )
    assert r.status_code == 200
    return today


def _scan(client, seeded):
    qr_token = client.get("/api/qr/token").json()["token"]
    return client.post("/api/scan", headers=seeded["staff_headers"], json={"qr_token": qr_token})


def _recent_scans(client, campus_id):
    r = client.get("/api/kiosk/recent-scans", params={"campus_id": campus_id})
    assert r.status_code == 200
    return r.json()["scans"]


def test_register_requires_birth_date(client, seeded):
    r = client.post(
        "/api/auth/register",
        json={
            "full_name": "Eksik Doğum",
            "phone": "0532 999 88 77",
            "job_title": "Öğretmen",
            "branch": "Fizik",
            "tc_kimlik_no": "22222222084",
            "campus_id": seeded["campus_a"]["id"],
            "device_fingerprint": "missing-bday-fp",
        },
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# One device → one identity (block registering two people on the same phone)
# --------------------------------------------------------------------------- #
def _register_staff(client, *, phone, device_fingerprint, campus_id, tc_kimlik_no="33333333026"):
    return client.post(
        "/api/auth/register",
        json={
            "full_name": "İkinci Personel",
            "phone": phone,
            "job_title": "Öğretmen",
            "branch": "Tarih",
            "birth_date": "1992-03-15",
            "tc_kimlik_no": tc_kimlik_no,
            "campus_id": campus_id,
            "device_fingerprint": device_fingerprint,
        },
    )


def test_same_device_cannot_register_second_staff(client, seeded):
    # Seeded "Ayşe Yılmaz" is bound to device "staff-fp-bbbbbbbb". A second,
    # different person must not be able to register from that same phone.
    r = _register_staff(
        client,
        phone="0532 444 55 66",
        device_fingerprint="staff-fp-bbbbbbbb",
        campus_id=seeded["campus_a"]["id"],
    )
    assert r.status_code == 409
    assert "başka bir personele tanımlı" in r.json()["detail"]


def test_second_staff_on_own_device_succeeds(client, seeded):
    # The block is per-device, not global: a different person on their own phone
    # registers normally.
    r = _register_staff(
        client,
        phone="0532 444 55 66",
        device_fingerprint="other-staff-fp-cccccccc",
        campus_id=seeded["campus_a"]["id"],
    )
    assert r.status_code == 201


def test_device_reusable_after_director_reset(client, seeded):
    # After the director clears Ayşe's device, that phone is free to bind a new
    # account again (recovery path for a re-used/handed-down handset).
    r = client.post(
        f"/api/staff/{seeded['staff_id']}/reset-device",
        headers=seeded["dir_a_headers"],
    )
    assert r.status_code == 200

    r = _register_staff(
        client,
        phone="0532 444 55 66",
        device_fingerprint="staff-fp-bbbbbbbb",
        campus_id=seeded["campus_a"]["id"],
    )
    assert r.status_code == 201


SEEDED_STAFF_PHONE = "0532 111 22 33"
SEEDED_STAFF_TC_KIMLIK_NO = "11111111042"


def test_existing_phone_new_device_rejected(client, seeded):
    # Knowing Ayşe's phone number is NOT enough: re-registering it from a
    # different device must be refused (both phone AND device must match).
    r = _register_staff(
        client,
        phone=SEEDED_STAFF_PHONE,
        device_fingerprint="attacker-device-zzzz",
        campus_id=seeded["campus_a"]["id"],
        tc_kimlik_no=SEEDED_STAFF_TC_KIMLIK_NO,
    )
    assert r.status_code == 409
    assert "başka bir cihaza tanımlı" in r.json()["detail"]


def test_existing_phone_same_device_reaccepted(client, seeded):
    # The genuine owner re-opening the app on the *same* device (e.g. reinstall)
    # is accepted and simply re-issued a session.
    r = _register_staff(
        client,
        phone=SEEDED_STAFF_PHONE,
        device_fingerprint="staff-fp-bbbbbbbb",
        campus_id=seeded["campus_a"]["id"],
        tc_kimlik_no=SEEDED_STAFF_TC_KIMLIK_NO,
    )
    assert r.status_code == 201


def test_existing_phone_new_device_allowed_after_reset(client, seeded):
    # A genuine phone change: the manager resets the device, then the same phone
    # number binds the new device.
    r = client.post(
        f"/api/staff/{seeded['staff_id']}/reset-device",
        headers=seeded["dir_a_headers"],
    )
    assert r.status_code == 200

    r = _register_staff(
        client,
        phone=SEEDED_STAFF_PHONE,
        device_fingerprint="ayse-new-phone-yyyy",
        campus_id=seeded["campus_a"]["id"],
        tc_kimlik_no=SEEDED_STAFF_TC_KIMLIK_NO,
    )
    assert r.status_code == 201


def test_existing_phone_wrong_tc_kimlik_rejected(client, seeded):
    # Even on the *same* device, a TC kimlik no that doesn't match the one on
    # file for this phone number is refused — the third leg of the match.
    r = _register_staff(
        client,
        phone=SEEDED_STAFF_PHONE,
        device_fingerprint="staff-fp-bbbbbbbb",
        campus_id=seeded["campus_a"]["id"],
        tc_kimlik_no="22222222084",
    )
    assert r.status_code == 409
    assert "TC kimlik" in r.json()["detail"]


def test_tc_kimlik_no_already_used_by_another_phone_rejected(client, seeded):
    # Reusing someone else's TC kimlik no on a brand-new phone+device is refused
    # — stops impersonating an existing employee's identity on another line.
    r = _register_staff(
        client,
        phone="0532 444 55 66",
        device_fingerprint="other-staff-fp-cccccccc",
        campus_id=seeded["campus_a"]["id"],
        tc_kimlik_no=SEEDED_STAFF_TC_KIMLIK_NO,
    )
    assert r.status_code == 409
    assert "TC kimlik" in r.json()["detail"]


def test_invalid_tc_kimlik_checksum_rejected(client, seeded):
    # A syntactically 11-digit but checksum-invalid TC kimlik no fails request
    # validation before any business logic runs.
    r = _register_staff(
        client,
        phone="0532 444 55 66",
        device_fingerprint="other-staff-fp-cccccccc",
        campus_id=seeded["campus_a"]["id"],
        tc_kimlik_no="12345678901",
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# Director rejects a pending self-registration (reuses disable/approve)
# --------------------------------------------------------------------------- #
def test_director_can_reject_pending_registration(client, seeded):
    phone = "0532 777 66 55"
    r = _register_staff(
        client,
        phone=phone,
        device_fingerprint="reject-fp-11111111",
        campus_id=seeded["campus_a"]["id"],
        tc_kimlik_no="55555555000",
    )
    assert r.status_code == 201
    new_staff_id = r.json()["user"]["id"]
    assert r.json()["user"]["status"] == "pending"

    r = client.post(f"/api/staff/{new_staff_id}/disable", headers=seeded["dir_a_headers"])
    assert r.status_code == 200
    assert r.json()["status"] == "disabled"

    # Rejected: re-registering with the same phone is refused, even on a new device.
    r2 = _register_staff(
        client,
        phone=phone,
        device_fingerprint="reject-fp-22222222",
        campus_id=seeded["campus_a"]["id"],
        tc_kimlik_no="55555555000",
    )
    assert r2.status_code == 403

    # The director can change their mind and reactivate the rejected account.
    r3 = client.post(f"/api/staff/{new_staff_id}/approve", headers=seeded["dir_a_headers"])
    assert r3.status_code == 200
    assert r3.json()["status"] == "active"

    # Now the same phone can register again and binds the new device.
    r4 = _register_staff(
        client,
        phone=phone,
        device_fingerprint="reject-fp-33333333",
        campus_id=seeded["campus_a"]["id"],
        tc_kimlik_no="55555555000",
    )
    assert r4.status_code == 201
    assert r4.json()["user"]["status"] == "active"


@pytest.mark.parametrize(
    "phone",
    [
        "0532 44 55",       # too short
        "0532 444 55 66 77",  # too long
        "0632 444 55 66",   # doesn't start with 5 after the trunk prefix
    ],
)
def test_malformed_phone_rejected_with_warning(client, seeded, phone):
    r = _register_staff(
        client,
        phone=phone,
        device_fingerprint="some-new-device-fp",
        campus_id=seeded["campus_a"]["id"],
    )
    assert r.status_code == 400
    assert r.json()["detail"]


def test_recent_scan_confirms_in_then_out(client, seeded):
    r = _scan(client, seeded)
    assert r.status_code == 200 and r.json()["type"] == "IN"

    scans = _recent_scans(client, seeded["campus_a"]["id"])
    assert len(scans) == 1
    assert scans[0]["full_name"] == "Ayşe Yılmaz"
    assert scans[0]["type"] == "IN"
    assert scans[0]["birthday"] is False

    r = _scan(client, seeded)
    assert r.status_code == 200 and r.json()["type"] == "OUT"

    scans = _recent_scans(client, seeded["campus_a"]["id"])
    types = {s["type"] for s in scans}
    assert types == {"IN", "OUT"}


def test_recent_scan_flags_birthday_first_in(client, seeded):
    _set_birthday_today(client, seeded)
    assert _scan(client, seeded).status_code == 200

    scans = _recent_scans(client, seeded["campus_a"]["id"])
    assert len(scans) == 1
    assert scans[0]["birthday"] is True
    assert scans[0]["full_name"] == "Ayşe Yılmaz"


def test_recent_scan_not_birthday_when_date_differs(client, seeded):
    # Seeded birthday is 1990-05-20; force a non-today date so the scan is a
    # plain confirmation, not a celebration.
    today = _today_local()
    other = (today + timedelta(days=1)).replace(year=1990)
    client.patch(
        f"/api/staff/{seeded['staff_id']}",
        headers=seeded["dir_a_headers"],
        json={"birth_date": other.isoformat()},
    )
    assert _scan(client, seeded).status_code == 200

    scans = _recent_scans(client, seeded["campus_a"]["id"])
    assert len(scans) == 1
    assert scans[0]["birthday"] is False


def test_manual_entry_not_in_recent_scans(client, seeded):
    today = _set_birthday_today(client, seeded)

    # A director's manual IN must NOT appear on the tablet — nobody scanned it.
    r = client.post(
        "/api/logs/manual",
        headers=seeded["dir_a_headers"],
        json={"user_id": seeded["staff_id"], "type": "IN", "date": today.isoformat(), "time": "00:00:00"},
    )
    assert r.status_code == 201

    assert _recent_scans(client, seeded["campus_a"]["id"]) == []


def test_recent_scans_scoped_to_campus(client, seeded):
    assert _scan(client, seeded).status_code == 200

    # A campus B kiosk must not see campus A's scan.
    assert _recent_scans(client, seeded["campus_b"]["id"]) == []


def test_recent_scans_scoped_to_kiosk_when_campus_has_several_tablets(client, seeded):
    """Two tablets at the same campus must not see each other's confirmations —
    only the tablet whose own QR code was actually scanned shows it."""
    campus_id = seeded["campus_a"]["id"]
    token = client.get(
        "/api/qr/token", params={"campus_id": campus_id, "kiosk_id": "tablet-1"}
    ).json()["token"]
    r = client.post("/api/scan", headers=seeded["staff_headers"], json={"qr_token": token})
    assert r.status_code == 200

    own = client.get(
        "/api/kiosk/recent-scans", params={"campus_id": campus_id, "kiosk_id": "tablet-1"}
    ).json()["scans"]
    assert len(own) == 1
    assert own[0]["full_name"] == "Ayşe Yılmaz"

    other = client.get(
        "/api/kiosk/recent-scans", params={"campus_id": campus_id, "kiosk_id": "tablet-2"}
    ).json()["scans"]
    assert other == []


# --------------------------------------------------------------------------- #
# One-time staff reset script (app.scripts.reset_staff)
# --------------------------------------------------------------------------- #
def test_reset_staff_preview_changes_nothing_then_confirm_wipes_staff(client, seeded):
    import asyncio

    # Give the staff member some history: a scan + a leave record.
    assert _scan(client, seeded).status_code == 200
    r = client.post(
        "/api/leaves",
        headers=seeded["dir_a_headers"],
        json={
            "user_id": seeded["staff_id"],
            "leave_type": "Ücretli izin",
            "start_date": "2026-06-02",
            "end_date": "2026-06-03",
        },
    )
    assert r.status_code == 201

    from app.database import AsyncSessionLocal
    from app.scripts.reset_staff import gather_counts, reset_staff

    async def _preview():
        async with AsyncSessionLocal() as s:
            return await gather_counts(s)

    counts = asyncio.run(_preview())
    assert counts["staff"] == 1
    assert counts["logs"] >= 1
    assert counts["leaves"] == 1

    # Preview must not have deleted anything: the staff member is still listed.
    rows = client.get("/api/staff", headers=seeded["dir_a_headers"]).json()
    assert any(row["id"] == seeded["staff_id"] for row in rows)

    async def _do():
        async with AsyncSessionLocal() as s:
            return await reset_staff(s)

    deleted = asyncio.run(_do())
    assert deleted["staff"] == 1

    # Staff gone; managers (directors + hq) untouched and still able to log in.
    rows = client.get("/api/staff", headers=seeded["dir_a_headers"]).json()
    assert rows == []
    dirs = client.get("/api/directors", headers=seeded["hq_headers"]).json()
    assert any(d["full_name"] == "Müdür A" for d in dirs)
    r = client.post(
        "/api/auth/login",
        json={"email": "director.a@test.com", "password": "DirPassword123!", "device_fingerprint": "dir-a-fp-aaaa"},
    )
    assert r.status_code == 200

    # And the same phone number can register fresh again (binding was cleared).
    r = client.post(
        "/api/auth/register",
        json={
            "full_name": "Ayşe Yılmaz",
            "phone": "0532 111 22 33",
            "job_title": "Öğretmen",
            "branch": "Matematik",
            "birth_date": "1990-05-20",
            "tc_kimlik_no": "11111111042",
            "campus_id": seeded["campus_a"]["id"],
            "device_fingerprint": "staff-fp-bbbbbbbb",
        },
    )
    assert r.status_code == 201
