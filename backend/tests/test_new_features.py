"""Integration tests for the three new workflows:

  1. Staff self-service leave requests (PWA) → director approve / reject.
  2. Per-person working days (rotational schedules) in absence reports.
  3. Official holidays / campus closures excluded from absence counting,
     plus the "unresolved status" (durum girilmedi) reminder endpoint.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def _today_local():
    return datetime.now(timezone.utc).astimezone(ZoneInfo("Europe/Istanbul")).date()


# --------------------------------------------------------------------------- #
# 1. Staff self-service leave requests
# --------------------------------------------------------------------------- #
def test_staff_leave_request_approve_blocks_scan(client, seeded):
    today = _today_local()
    # Staff submits their own request covering today.
    r = client.post(
        "/api/leaves/requests",
        headers=seeded["staff_headers"],
        json={
            "leave_type": "Ücretli izin",
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=1)).isoformat(),
            "note": "Ailevi sebep",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "requested"
    assert body["self_requested"] is True
    leave_id = body["id"]

    # A requested (not yet approved) leave must NOT block scanning.
    qr_token = client.get("/api/qr/token").json()["token"]
    r = client.post("/api/scan", headers=seeded["staff_headers"], json={"qr_token": qr_token})
    assert r.status_code == 200

    # Director sees it as a pending request and approves it.
    r = client.get(
        "/api/leaves",
        headers=seeded["dir_a_headers"],
        params={"status": "requested"},
    )
    assert any(row["id"] == leave_id for row in r.json())

    r = client.post(f"/api/leaves/{leave_id}/approve", headers=seeded["dir_a_headers"])
    assert r.status_code == 200
    approved = r.json()
    assert approved["status"] == "active"
    assert approved["decided_by_name"] == "Müdür A"

    # Now active → scanning is blocked for the covered range.
    qr_token = client.get("/api/qr/token").json()["token"]
    r = client.post("/api/scan", headers=seeded["staff_headers"], json={"qr_token": qr_token})
    assert r.status_code == 409
    assert "Ücretli izin" in r.json()["detail"]


def test_staff_leave_request_reject_does_not_block(client, seeded):
    today = _today_local()
    r = client.post(
        "/api/leaves/requests",
        headers=seeded["staff_headers"],
        json={
            "leave_type": "Mazeret izni",
            "start_date": today.isoformat(),
            "end_date": today.isoformat(),
        },
    )
    leave_id = r.json()["id"]

    r = client.post(f"/api/leaves/{leave_id}/reject", headers=seeded["dir_a_headers"])
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"

    # Rejected blocks nothing.
    qr_token = client.get("/api/qr/token").json()["token"]
    r = client.post("/api/scan", headers=seeded["staff_headers"], json={"qr_token": qr_token})
    assert r.status_code == 200

    # Cannot approve an already-decided request.
    r = client.post(f"/api/leaves/{leave_id}/approve", headers=seeded["dir_a_headers"])
    assert r.status_code == 409


def test_staff_lists_own_leaves(client, seeded):
    today = _today_local()
    client.post(
        "/api/leaves/requests",
        headers=seeded["staff_headers"],
        json={
            "leave_type": "Ücretsiz izin",
            "start_date": (today + timedelta(days=3)).isoformat(),
            "end_date": (today + timedelta(days=4)).isoformat(),
        },
    )
    r = client.get("/api/leaves/me", headers=seeded["staff_headers"])
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["leave_type"] == "Ücretsiz izin"


def test_director_cannot_decide_other_campus_request(client, seeded):
    today = _today_local()
    r = client.post(
        "/api/leaves/requests",
        headers=seeded["staff_headers"],
        json={
            "leave_type": "Ücretli izin",
            "start_date": today.isoformat(),
            "end_date": today.isoformat(),
        },
    )
    leave_id = r.json()["id"]
    # Director B (other campus) may not approve campus A's staff request.
    r = client.post(f"/api/leaves/{leave_id}/approve", headers=seeded["dir_b_headers"])
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# 2. Per-person working days
# --------------------------------------------------------------------------- #
def test_working_days_set_via_staff_patch(client, seeded):
    r = client.patch(
        f"/api/staff/{seeded['staff_id']}",
        headers=seeded["dir_a_headers"],
        json={"working_days": [1, 2, 3]},  # Mon, Tue, Wed only
    )
    assert r.status_code == 200
    assert r.json()["working_days"] == [1, 2, 3]

    # Listing reflects it too.
    r = client.get("/api/staff", headers=seeded["dir_a_headers"])
    me = next(u for u in r.json() if u["id"] == seeded["staff_id"])
    assert me["working_days"] == [1, 2, 3]


def test_working_days_exclude_nonworking_from_absences(client, seeded):
    # Pick a Thursday so it is a weekday (would normally count as an absence)
    # but NOT in a Mon–Wed schedule.
    base = _today_local() - timedelta(days=40)
    thursday = base + timedelta(days=(3 - base.weekday()) % 7)
    assert thursday.isoweekday() == 4

    client.patch(
        f"/api/staff/{seeded['staff_id']}",
        headers=seeded["dir_a_headers"],
        json={"working_days": [1, 2, 3]},
    )

    r = client.get(
        "/api/reports/absences",
        headers=seeded["dir_a_headers"],
        params={
            "start_date": thursday.isoformat(),
            "end_date": thursday.isoformat(),
            "exclude_weekends": "false",
        },
    )
    assert r.status_code == 200
    # Thursday is not a working day for this person → no absence row.
    assert r.json() == []


def test_working_days_cleared_back_to_default(client, seeded):
    client.patch(
        f"/api/staff/{seeded['staff_id']}",
        headers=seeded["dir_a_headers"],
        json={"working_days": [1, 2, 3]},
    )
    r = client.patch(
        f"/api/staff/{seeded['staff_id']}",
        headers=seeded["dir_a_headers"],
        json={"working_days": []},
    )
    assert r.status_code == 200
    assert r.json()["working_days"] is None


# --------------------------------------------------------------------------- #
# 3. Holidays + unresolved reminder
# --------------------------------------------------------------------------- #
def test_holiday_excluded_from_absences(client, seeded):
    # A Wednesday well in the past (a weekday, normally an absence).
    base = _today_local() - timedelta(days=40)
    wednesday = base + timedelta(days=(2 - base.weekday()) % 7)
    assert wednesday.isoweekday() == 3

    # Without a holiday, the day is an unresolved absence.
    r = client.get(
        "/api/reports/absences",
        headers=seeded["dir_a_headers"],
        params={
            "start_date": wednesday.isoformat(),
            "end_date": wednesday.isoformat(),
            "exclude_weekends": "false",
        },
    )
    assert any(row["status"] == "unresolved" for row in r.json())

    # National holiday on that date.
    r = client.post(
        "/api/holidays",
        headers=seeded["hq_headers"],
        json={"date": wednesday.isoformat(), "name": "Resmi Tatil"},
    )
    assert r.status_code == 201
    assert r.json()["campus_id"] is None

    r = client.get(
        "/api/reports/absences",
        headers=seeded["dir_a_headers"],
        params={
            "start_date": wednesday.isoformat(),
            "end_date": wednesday.isoformat(),
            "exclude_weekends": "false",
        },
    )
    assert r.json() == []


def test_director_creates_own_campus_holiday(client, seeded):
    base = _today_local() - timedelta(days=30)
    monday = base + timedelta(days=(0 - base.weekday()) % 7)

    r = client.post(
        "/api/holidays",
        headers=seeded["dir_a_headers"],
        json={"date": monday.isoformat(), "name": "Kampüs Kapanışı"},
    )
    assert r.status_code == 201
    assert r.json()["campus_id"] == seeded["campus_a"]["id"]

    # Director B does not see campus A's local closure.
    r = client.get("/api/holidays", headers=seeded["dir_b_headers"])
    assert all(h["date"] != monday.isoformat() for h in r.json())


def test_director_cannot_delete_national_holiday(client, seeded):
    base = _today_local() - timedelta(days=25)
    r = client.post(
        "/api/holidays",
        headers=seeded["hq_headers"],
        json={"date": base.isoformat(), "name": "Ulusal Bayram"},
    )
    holiday_id = r.json()["id"]

    r = client.delete(f"/api/holidays/{holiday_id}", headers=seeded["dir_a_headers"])
    assert r.status_code == 403

    r = client.delete(f"/api/holidays/{holiday_id}", headers=seeded["hq_headers"])
    assert r.status_code == 204


def test_duplicate_holiday_rejected(client, seeded):
    base = _today_local() - timedelta(days=20)
    payload = {"date": base.isoformat(), "name": "Tatil"}
    r = client.post("/api/holidays", headers=seeded["hq_headers"], json=payload)
    assert r.status_code == 201
    r = client.post("/api/holidays", headers=seeded["hq_headers"], json=payload)
    assert r.status_code == 409


def test_unresolved_reminder_counts_recent_gaps(client, seeded):
    r = client.get(
        "/api/reports/unresolved-reminder",
        headers=seeded["dir_a_headers"],
        params={"days": 10, "exclude_weekends": "false"},
    )
    assert r.status_code == 200
    body = r.json()
    # The seeded staff member never scanned, so recent weekdays are unresolved.
    assert body["unresolved_count"] > 0
    assert all(e["status"] == "unresolved" for e in body["entries"])
    # The window ends yesterday, never today.
    assert body["end_date"] < _today_local().isoformat()
