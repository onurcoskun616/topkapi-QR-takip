"""Monthly hours / payroll (puantaj) report.

Covers the worked-hours math (first IN → last OUT), the present/complete-day
counts, cumulative lateness vs the campus shift, and the absent/leave split
over a staff member's scheduled days — plus the .xlsx export.
"""
from datetime import date, timedelta


def _manual(client, headers, user_id, type_, day, time_):
    r = client.post(
        "/api/logs/manual",
        headers=headers,
        json={"user_id": user_id, "type": type_, "date": day.isoformat(), "time": time_},
    )
    assert r.status_code == 201, r.text


def test_monthly_hours_worked_and_late(client, seeded):
    # Use a fixed past month so the range is fully in the past and stable.
    # Campus A shift is 08:00–17:00 (set in the seeded fixture).
    year, month = 2025, 3
    # 2025-03-03 is a Monday; 03-04 a Tuesday — both weekdays.
    d1 = date(2025, 3, 3)
    d2 = date(2025, 3, 4)
    headers = seeded["dir_a_headers"]
    staff_id = seeded["staff_id"]

    # Day 1: on time (08:00) → 17:00 = 9h, not late.
    _manual(client, headers, staff_id, "IN", d1, "08:00:00")
    _manual(client, headers, staff_id, "OUT", d1, "17:00:00")
    # Day 2: 30 min late (08:30) → 16:30 = 8h, 30 min late.
    _manual(client, headers, staff_id, "IN", d2, "08:30:00")
    _manual(client, headers, staff_id, "OUT", d2, "16:30:00")

    r = client.get(
        "/api/reports/monthly-hours",
        headers=headers,
        params={"year": year, "month": month, "exclude_weekends": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["year"] == year and body["month"] == month
    assert body["start_date"] == "2025-03-01"
    assert body["end_date"] == "2025-03-31"

    entry = next(e for e in body["entries"] if e["user_id"] == staff_id)
    assert entry["present_days"] == 2
    assert entry["worked_days"] == 2
    assert entry["total_hours"] == 17.0  # 9h + 8h
    assert entry["total_late_minutes"] == 30
    # March 2025 has 21 weekdays; the staff worked 2, so 19 unresolved absences.
    assert entry["expected_days"] == 21
    assert entry["leave_days"] == 0
    assert entry["absent_days"] == 19


def test_monthly_hours_leave_excluded_from_absences(client, seeded):
    year, month = 2025, 3
    headers = seeded["dir_a_headers"]
    staff_id = seeded["staff_id"]

    # A whole-month leave → every scheduled day is "izinli", none "devamsız".
    client.post(
        "/api/leaves",
        headers=headers,
        json={
            "user_id": staff_id,
            "leave_type": "Ücretli izin",
            "start_date": "2025-03-01",
            "end_date": "2025-03-31",
        },
    )

    r = client.get(
        "/api/reports/monthly-hours",
        headers=headers,
        params={"year": year, "month": month, "exclude_weekends": True},
    )
    assert r.status_code == 200, r.text
    entry = next(e for e in r.json()["entries"] if e["user_id"] == staff_id)
    assert entry["absent_days"] == 0
    assert entry["leave_days"] == entry["expected_days"]


def test_monthly_hours_incomplete_day_counts_present_not_worked(client, seeded):
    year, month = 2025, 3
    headers = seeded["dir_a_headers"]
    staff_id = seeded["staff_id"]

    # Only an IN, no OUT → the day is "present" but not a complete worked day.
    _manual(client, headers, staff_id, "IN", date(2025, 3, 3), "08:00:00")

    r = client.get(
        "/api/reports/monthly-hours",
        headers=headers,
        params={"year": year, "month": month, "exclude_weekends": True},
    )
    entry = next(e for e in r.json()["entries"] if e["user_id"] == staff_id)
    assert entry["present_days"] == 1
    assert entry["worked_days"] == 0
    assert entry["total_hours"] == 0.0


def test_monthly_hours_director_scoped_to_own_campus(client, seeded):
    # Campus B's director sees only campus B staff (none seeded there) — the
    # campus A staff member must not appear.
    r = client.get(
        "/api/reports/monthly-hours",
        headers=seeded["dir_b_headers"],
        params={"year": 2025, "month": 3},
    )
    assert r.status_code == 200
    assert all(e["user_id"] != seeded["staff_id"] for e in r.json()["entries"])


def test_monthly_hours_xlsx_download(client, seeded):
    _manual(client, seeded["dir_a_headers"], seeded["staff_id"], "IN", date(2025, 3, 3), "08:00:00")
    _manual(client, seeded["dir_a_headers"], seeded["staff_id"], "OUT", date(2025, 3, 3), "17:00:00")

    r = client.get(
        "/api/reports/monthly-hours.xlsx",
        headers=seeded["dir_a_headers"],
        params={"year": 2025, "month": 3},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert r.content[:2] == b"PK"  # xlsx is a zip archive
