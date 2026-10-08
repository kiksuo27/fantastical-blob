from tests.conftest import TestingSessionLocal
from auth import hash_password
import models


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def make_admin(client, org_id, email, super_admin=False):
    db = TestingSessionLocal()
    admin = models.User(
        name=f"Admin {email}",
        jersey_number=0, position="staff", year=0,
        email=email,
        password_hash=hash_password("adminpass123"),
        role="admin",
        is_super_admin=super_admin,
        organization_id=org_id,
    )
    db.add(admin)
    db.commit()
    db.close()
    login = client.post("/login", json={"email": email, "password": "adminpass123"})
    return login.json()["access_token"]


def make_player(client, admin_token, name, email, position="WR"):
    created = client.post(
        "/users",
        json={"name": name, "jersey_number": 10, "position": position,
              "year": 1, "email": email, "role": "player"},
        headers=auth(admin_token),
    )
    assert created.status_code == 200
    user_id = created.json()["id"]
    client.post("/claim-account", json={"email": email, "password": "playerpass123"})
    login = client.post("/login", json={"email": email, "password": "playerpass123"})
    return login.json()["access_token"], user_id


def two_orgs(client, test_org, second_org):
    # Both admins are super admins on purpose, so the reset endpoint is a real test
    a = make_admin(client, test_org, "a_admin@test.com", super_admin=True)
    b = make_admin(client, second_org, "b_admin@test.com", super_admin=True)
    a_token, a_pid = make_player(client, a, "Alpha Player", "alpha@test.com", position="QB")
    b_token, b_pid = make_player(client, b, "Bravo Player", "bravo@test.com", position="WR")
    return a, b, a_token, a_pid, b_token, b_pid


def make_assessment(client, admin_token):
    r = client.post("/assessments",
                    json={"title": "Iso Test", "is_public": True, "assessment_type": "player"},
                    headers=auth(admin_token))
    assessment_id = r.json()["id"]
    q = client.post(f"/assessments/{assessment_id}/questions",
                    json={"question_text": "Q", "question_type": "rating", "value_points": 20},
                    headers=auth(admin_token)).json()
    return assessment_id, q["id"]


def submit(client, token, assessment_id, question_id, value):
    r = client.post(
        f"/assessments/{assessment_id}/submit",
        json={"answers": [{"question_id": question_id, "answer_value": value, "answer_text": None}]},
        headers=auth(token),
    )
    assert r.status_code == 200


def test_roster_and_search_scoped_to_org(client, db_session, test_org, second_org):
    a, b, _, a_pid, _, b_pid = two_orgs(client, test_org, second_org)

    a_ids = [u["id"] for u in client.get("/users", headers=auth(a)).json()]
    b_ids = [u["id"] for u in client.get("/users", headers=auth(b)).json()]
    assert a_pid in a_ids and b_pid not in a_ids
    assert b_pid in b_ids and a_pid not in b_ids

    assert all("Alpha" not in r["title"] for r in client.get("/search?q=Alpha", headers=auth(b)).json())
    assert any("Alpha" in r["title"] for r in client.get("/search?q=Alpha", headers=auth(a)).json())


def test_by_id_user_endpoints_blocked_across_orgs(client, db_session, test_org, second_org):
    a, b, a_ptoken, a_pid, _, _ = two_orgs(client, test_org, second_org)
    assessment_id, qid = make_assessment(client, a)
    submit(client, a_ptoken, assessment_id, qid, 20)

    attempts = [
        client.put(f"/users/{a_pid}", json={"name": "Hacked"}, headers=auth(b)),
        client.get(f"/users/{a_pid}/proficiency", headers=auth(b)),
        client.get(f"/users/{a_pid}/category-breakdown", headers=auth(b)),
        client.get(f"/assessments/{assessment_id}/users/{a_pid}/latest-attempt", headers=auth(b)),
        client.get(f"/assessments/{assessment_id}/users/{a_pid}/attempt-detail", headers=auth(b)),
        client.get(f"/users/{a_pid}/resumes", headers=auth(b)),
        client.get(f"/community-service/users/{a_pid}", headers=auth(b)),
        client.post("/touchpoints", json={"user_id": a_pid, "meeting_type": "Life Skills"}, headers=auth(b)),
        client.delete(f"/assessments/{assessment_id}/users/{a_pid}/reset", headers=auth(b)),
        client.delete(f"/users/{a_pid}", headers=auth(b)),
    ]
    for r in attempts:
        assert r.status_code == 404, f"{r.request.method} {r.request.url} returned {r.status_code}"

    # Nothing about A's player changed
    users_a = {u["id"]: u for u in client.get("/users", headers=auth(a)).json()}
    assert users_a[a_pid]["name"] == "Alpha Player"
    assert client.get(f"/assessments/{assessment_id}/users/{a_pid}/latest-attempt",
                      headers=auth(a)).status_code == 200


def test_user_archive_scoped_to_org(client, db_session, test_org, second_org):
    a, b, _, a_pid, _, _ = two_orgs(client, test_org, second_org)
    assert client.delete(f"/users/{a_pid}", headers=auth(a)).status_code == 200

    assert a_pid not in [u["id"] for u in client.get("/archive/users", headers=auth(b)).json()]
    assert a_pid in [u["id"] for u in client.get("/archive/users", headers=auth(a)).json()]
    assert client.post(f"/archive/users/{a_pid}/restore", headers=auth(b)).status_code == 404
    assert client.delete(f"/archive/users/{a_pid}/permanent", headers=auth(b)).status_code == 404
    assert a_pid in [u["id"] for u in client.get("/archive/users", headers=auth(a)).json()]


def test_update_cannot_move_user_between_orgs(client, db_session, test_org, second_org):
    a, b, _, a_pid, _, _ = two_orgs(client, test_org, second_org)
    client.put(f"/users/{a_pid}", json={"name": "Renamed", "organization_id": second_org}, headers=auth(a))

    assert a_pid in [u["id"] for u in client.get("/users", headers=auth(a)).json()]
    assert a_pid not in [u["id"] for u in client.get("/users", headers=auth(b)).json()]


def test_analytics_scoped_to_org(client, db_session, test_org, second_org):
    a, b, a_ptoken, _, b_ptoken, _ = two_orgs(client, test_org, second_org)
    assessment_id, qid = make_assessment(client, a)
    submit(client, a_ptoken, assessment_id, qid, 20)
    submit(client, b_ptoken, assessment_id, qid, 10)

    q = f"assessment_id={assessment_id}"
    assert client.get(f"/analytics/team-average?{q}", headers=auth(a)).json()["average_score"] == 20
    assert client.get(f"/analytics/team-average?{q}", headers=auth(b)).json()["average_score"] == 10

    pos_a = [p["position"] for p in client.get(f"/analytics/by-position?{q}", headers=auth(a)).json()]
    pos_b = [p["position"] for p in client.get(f"/analytics/by-position?{q}", headers=auth(b)).json()]
    assert pos_a == ["QB"]
    assert pos_b == ["WR"]

def test_remaining_analytics_scoped_to_org(client, db_session, test_org, second_org):
    a, b, a_ptoken, _, b_ptoken, _ = two_orgs(client, test_org, second_org)

    assessment_id = client.post(
        "/assessments",
        json={"title": "Iso Analytics", "is_public": True, "assessment_type": "player"},
        headers=auth(a),
    ).json()["id"]
    qid = client.post(
        f"/assessments/{assessment_id}/questions",
        json={"question_text": "Q", "question_type": "rating", "category": "Focus", "value_points": 20},
        headers=auth(a),
    ).json()["id"]

    for token, value, seconds in ((a_ptoken, 20, 1.0), (b_ptoken, 10, 3.0)):
        r = client.post(
            f"/assessments/{assessment_id}/submit",
            json={"answers": [{"question_id": qid, "answer_value": value,
                               "answer_text": None, "time_taken_seconds": seconds}],
                  "duration_seconds": 30.0},
            headers=auth(token),
        )
        assert r.status_code == 200

    q = f"assessment_id={assessment_id}"

    cat_a = client.get(f"/analytics/by-category?{q}", headers=auth(a)).json()
    cat_b = client.get(f"/analytics/by-category?{q}", headers=auth(b)).json()
    assert cat_a[0]["average_score"] == 20 and cat_a[0]["response_count"] == 1
    assert cat_b[0]["average_score"] == 10 and cat_b[0]["response_count"] == 1

    trend_a = client.get(f"/analytics/trend?{q}", headers=auth(a)).json()
    trend_b = client.get(f"/analytics/trend?{q}", headers=auth(b)).json()
    assert [t["average_score"] for t in trend_a] == [20]
    assert [t["average_score"] for t in trend_b] == [10]

    time_a = client.get(f"/analytics/category-timing?{q}", headers=auth(a)).json()
    time_b = client.get(f"/analytics/category-timing?{q}", headers=auth(b)).json()
    assert time_a[0]["average_seconds"] == 1.0
    assert time_b[0]["average_seconds"] == 3.0

    rapid_a = client.get(f"/analytics/rapid-responses?{q}", headers=auth(a)).json()
    rapid_b = client.get(f"/analytics/rapid-responses?{q}", headers=auth(b)).json()
    assert rapid_a[0]["total_count"] == 1 and rapid_a[0]["rapid_count"] == 1
    assert rapid_b == []