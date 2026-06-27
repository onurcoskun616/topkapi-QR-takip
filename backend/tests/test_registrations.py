"""Integration tests for student registration tracking:

  * Departments + MEB license quota (ruhsat kontenjanı) — head-office managed.
  * Per-grade internal/external registration targets (kayıt hedefi).
  * Student registrations counting toward quota/targets only when *registered*
    and *approved*, classified internal/external by arrival channel.
  * Campus scoping for directors.
"""


def _make_department(client, hq_headers, campus_id, name="Anadolu Lisesi", quota=3):
    r = client.post(
        "/api/departments",
        headers=hq_headers,
        json={"campus_id": campus_id, "name": name, "license_quota": quota},
    )
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# Departments + targets (hq manages; directors read-only)
# --------------------------------------------------------------------------- #
def test_hq_creates_department_and_sets_targets(client, seeded):
    dept = _make_department(client, seeded["hq_headers"], seeded["campus_a"]["id"])
    assert dept["license_quota"] == 3
    assert dept["confirmed_count"] == 0
    assert dept["remaining_quota"] == 3
    # All four grades present, defaulting to 0/0.
    assert [t["grade"] for t in dept["targets"]] == [9, 10, 11, 12]

    r = client.put(
        f"/api/departments/{dept['id']}/targets",
        headers=seeded["hq_headers"],
        json={
            "targets": [
                {"grade": 9, "internal_target": 10, "external_target": 20},
                {"grade": 10, "internal_target": 5, "external_target": 8},
            ]
        },
    )
    assert r.status_code == 200, r.text
    by_grade = {t["grade"]: t for t in r.json()["targets"]}
    assert by_grade[9] == {"grade": 9, "internal_target": 10, "external_target": 20}
    assert by_grade[11] == {"grade": 11, "internal_target": 0, "external_target": 0}


def test_director_cannot_create_department(client, seeded):
    r = client.post(
        "/api/departments",
        headers=seeded["dir_a_headers"],
        json={"campus_id": seeded["campus_a"]["id"], "name": "Fen Lisesi", "license_quota": 5},
    )
    assert r.status_code == 403


def test_director_sees_only_own_campus_departments(client, seeded):
    _make_department(client, seeded["hq_headers"], seeded["campus_a"]["id"], name="A-Bölüm")
    _make_department(client, seeded["hq_headers"], seeded["campus_b"]["id"], name="B-Bölüm")

    rows = client.get("/api/departments", headers=seeded["dir_a_headers"]).json()
    assert {d["name"] for d in rows} == {"A-Bölüm"}

    all_rows = client.get("/api/departments", headers=seeded["hq_headers"]).json()
    assert {d["name"] for d in all_rows} >= {"A-Bölüm", "B-Bölüm"}


def test_duplicate_department_name_rejected(client, seeded):
    _make_department(client, seeded["hq_headers"], seeded["campus_a"]["id"], name="Dup")
    r = client.post(
        "/api/departments",
        headers=seeded["hq_headers"],
        json={"campus_id": seeded["campus_a"]["id"], "name": "Dup", "license_quota": 1},
    )
    assert r.status_code == 409


# --------------------------------------------------------------------------- #
# Registrations count only when registered + approved
# --------------------------------------------------------------------------- #
def _register(client, headers, dept_id, **over):
    body = {
        "department_id": dept_id,
        "full_name": "Öğrenci Bir",
        "grade": 9,
        "section": "A",
        "arrival_channel": "Reklam",
        "status": "prospective",
        "approved": False,
    }
    body.update(over)
    return client.post("/api/registrations", headers=headers, json=body)


def test_prospective_registration_does_not_count(client, seeded):
    dept = _make_department(client, seeded["hq_headers"], seeded["campus_a"]["id"])
    r = _register(client, seeded["dir_a_headers"], dept["id"])
    assert r.status_code == 201
    body = r.json()
    assert body["counts_toward_target"] is False
    assert body["is_internal"] is False  # "Reklam" is external

    # Department still shows zero confirmed.
    rows = client.get("/api/departments", headers=seeded["dir_a_headers"]).json()
    assert rows[0]["confirmed_count"] == 0


def test_registered_but_unapproved_does_not_count(client, seeded):
    dept = _make_department(client, seeded["hq_headers"], seeded["campus_a"]["id"])
    r = _register(client, seeded["dir_a_headers"], dept["id"], status="registered")
    assert r.json()["counts_toward_target"] is False

    summary = client.get("/api/registrations/summary", headers=seeded["dir_a_headers"]).json()
    dep = next(d for d in summary["departments"] if d["department_id"] == dept["id"])
    assert dep["confirmed_count"] == 0


def test_registered_and_approved_counts_toward_external_target(client, seeded):
    dept = _make_department(client, seeded["hq_headers"], seeded["campus_a"]["id"])
    reg = _register(
        client, seeded["dir_a_headers"], dept["id"], status="registered", arrival_channel="Tavsiye"
    ).json()
    r = client.post(f"/api/registrations/{reg['id']}/approve", headers=seeded["dir_a_headers"])
    assert r.status_code == 200
    body = r.json()
    assert body["counts_toward_target"] is True
    assert body["approved"] is True
    assert body["approved_by_name"] == "Müdür A"

    summary = client.get("/api/registrations/summary", headers=seeded["dir_a_headers"]).json()
    dep = next(d for d in summary["departments"] if d["department_id"] == dept["id"])
    assert dep["confirmed_count"] == 1
    grade9 = next(g for g in dep["grades"] if g["grade"] == 9)
    assert grade9["external_count"] == 1
    assert grade9["internal_count"] == 0


def test_internal_channel_counts_toward_internal_target(client, seeded):
    dept = _make_department(client, seeded["hq_headers"], seeded["campus_a"]["id"])
    reg = _register(
        client, seeded["dir_a_headers"], dept["id"],
        status="registered", arrival_channel="İç Kayıt",
    ).json()
    assert reg["is_internal"] is True
    client.post(f"/api/registrations/{reg['id']}/approve", headers=seeded["dir_a_headers"])

    summary = client.get("/api/registrations/summary", headers=seeded["dir_a_headers"]).json()
    dep = next(d for d in summary["departments"] if d["department_id"] == dept["id"])
    grade9 = next(g for g in dep["grades"] if g["grade"] == 9)
    assert grade9["internal_count"] == 1
    assert grade9["external_count"] == 0


def test_lowercase_internal_channel_still_internal(client, seeded):
    """A hand-typed 'iç kayıt' must classify as internal too."""
    dept = _make_department(client, seeded["hq_headers"], seeded["campus_a"]["id"])
    reg = _register(
        client, seeded["dir_a_headers"], dept["id"],
        status="registered", arrival_channel="iç kayıt",
    ).json()
    assert reg["is_internal"] is True


# --------------------------------------------------------------------------- #
# License quota enforcement
# --------------------------------------------------------------------------- #
def test_quota_blocks_over_capacity_approval(client, seeded):
    dept = _make_department(client, seeded["hq_headers"], seeded["campus_a"]["id"], quota=2)
    ids = []
    for i in range(3):
        reg = _register(
            client, seeded["dir_a_headers"], dept["id"],
            full_name=f"Öğrenci {i}", status="registered",
        ).json()
        ids.append(reg["id"])

    # First two approvals fill the quota.
    assert client.post(f"/api/registrations/{ids[0]}/approve", headers=seeded["dir_a_headers"]).status_code == 200
    assert client.post(f"/api/registrations/{ids[1]}/approve", headers=seeded["dir_a_headers"]).status_code == 200
    # Third exceeds the MEB license quota.
    r = client.post(f"/api/registrations/{ids[2]}/approve", headers=seeded["dir_a_headers"])
    assert r.status_code == 409

    # Withdrawing one frees a slot so the third can be approved.
    client.post(f"/api/registrations/{ids[0]}/unapprove", headers=seeded["dir_a_headers"])
    r = client.post(f"/api/registrations/{ids[2]}/approve", headers=seeded["dir_a_headers"])
    assert r.status_code == 200

    rows = client.get("/api/departments", headers=seeded["dir_a_headers"]).json()
    assert rows[0]["confirmed_count"] == 2
    assert rows[0]["remaining_quota"] == 0


def test_create_already_confirmed_respects_quota(client, seeded):
    dept = _make_department(client, seeded["hq_headers"], seeded["campus_a"]["id"], quota=1)
    assert _register(
        client, seeded["dir_a_headers"], dept["id"], status="registered", approved=True
    ).status_code == 201
    # Second confirmed create over quota is rejected.
    r = _register(
        client, seeded["dir_a_headers"], dept["id"],
        full_name="Öğrenci İki", status="registered", approved=True,
    )
    assert r.status_code == 409


# --------------------------------------------------------------------------- #
# Scoping for student registrations
# --------------------------------------------------------------------------- #
def test_director_cannot_register_into_other_campus_department(client, seeded):
    dept_b = _make_department(client, seeded["hq_headers"], seeded["campus_b"]["id"], name="B-Dept")
    r = _register(client, seeded["dir_a_headers"], dept_b["id"])
    assert r.status_code == 403


def test_director_cannot_touch_other_campus_registration(client, seeded):
    dept_b = _make_department(client, seeded["hq_headers"], seeded["campus_b"]["id"], name="B-Dept")
    reg = _register(client, seeded["dir_b_headers"], dept_b["id"]).json()
    # Director A cannot approve or delete a campus-B registration.
    assert client.post(f"/api/registrations/{reg['id']}/approve", headers=seeded["dir_a_headers"]).status_code == 403
    assert client.delete(f"/api/registrations/{reg['id']}", headers=seeded["dir_a_headers"]).status_code == 403
    # And it never appears in director A's list.
    rows = client.get("/api/registrations", headers=seeded["dir_a_headers"]).json()
    assert all(row["id"] != reg["id"] for row in rows)


# --------------------------------------------------------------------------- #
# Search form filters
# --------------------------------------------------------------------------- #
def test_registration_search_filters(client, seeded):
    dept = _make_department(client, seeded["hq_headers"], seeded["campus_a"]["id"])
    _register(client, seeded["dir_a_headers"], dept["id"], full_name="Ali Veli", grade=9, arrival_channel="İç Kayıt")
    _register(client, seeded["dir_a_headers"], dept["id"], full_name="Veli Ali", grade=10, arrival_channel="Reklam")

    # Filter by grade.
    rows = client.get("/api/registrations", headers=seeded["dir_a_headers"], params={"grade": 10}).json()
    assert {r["full_name"] for r in rows} == {"Veli Ali"}

    # Filter by name query.
    rows = client.get("/api/registrations", headers=seeded["dir_a_headers"], params={"q": "ali"}).json()
    assert {r["full_name"] for r in rows} == {"Ali Veli", "Veli Ali"}

    # Filter by arrival channel.
    rows = client.get("/api/registrations", headers=seeded["dir_a_headers"], params={"channel": "Reklam"}).json()
    assert {r["full_name"] for r in rows} == {"Veli Ali"}


def test_delete_department_with_students_rejected(client, seeded):
    dept = _make_department(client, seeded["hq_headers"], seeded["campus_a"]["id"])
    _register(client, seeded["dir_a_headers"], dept["id"])
    r = client.delete(f"/api/departments/{dept['id']}", headers=seeded["hq_headers"])
    assert r.status_code == 409
