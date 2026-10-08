from tests.conftest import TestingSessionLocal
from auth import hash_password
import models


def make_admin_in_org(client, org_id, email):
    db = TestingSessionLocal()
    admin = models.User(
        name="Isolation Admin",
        jersey_number=0,
        position="staff",
        year=0,
        email=email,
        password_hash=hash_password("adminpass123"),
        role="admin",
        organization_id=org_id
    )
    db.add(admin)
    db.commit()
    db.close()

    login = client.post("/login", json={"email": email, "password": "adminpass123"})
    return login.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def create_course_as(client, token, title="Org A Course"):
    # is_public=True on purpose: a public course in another org must still be invisible
    r = client.post("/courses", json={"title": title, "is_public": True}, headers=auth(token))
    assert r.status_code == 200
    return r.json()["id"]


def test_course_not_accessible_across_orgs(client, db_session, test_org, second_org):
    a = make_admin_in_org(client, test_org, "a_admin@test.com")
    b = make_admin_in_org(client, second_org, "b_admin@test.com")
    course_id = create_course_as(client, a)

    # B's list must not include A's course; A's must
    assert course_id not in [c["id"] for c in client.get("/courses", headers=auth(b)).json()]
    assert course_id in [c["id"] for c in client.get("/courses", headers=auth(a)).json()]

    # B cannot read, edit, delete, or add modules to it
    assert client.get(f"/courses/{course_id}", headers=auth(b)).status_code == 404
    assert client.put(f"/courses/{course_id}", json={"title": "Hacked"}, headers=auth(b)).status_code == 404
    assert client.delete(f"/courses/{course_id}", headers=auth(b)).status_code == 404
    assert client.post(
        f"/courses/{course_id}/modules",
        json={"title": "Injected", "content": "x", "order_index": 0},
        headers=auth(b)
    ).status_code == 404

    # A's course is untouched by all of that
    r = client.get(f"/courses/{course_id}", headers=auth(a))
    assert r.status_code == 200
    assert r.json()["title"] == "Org A Course"


def test_archive_not_accessible_across_orgs(client, db_session, test_org, second_org):
    a = make_admin_in_org(client, test_org, "a_admin@test.com")
    b = make_admin_in_org(client, second_org, "b_admin@test.com")
    course_id = create_course_as(client, a)
    assert client.delete(f"/courses/{course_id}", headers=auth(a)).status_code == 200

    assert course_id not in [c["id"] for c in client.get("/archive/courses", headers=auth(b)).json()]
    assert course_id in [c["id"] for c in client.get("/archive/courses", headers=auth(a)).json()]

    # The dangerous one: B must not be able to restore or permanently delete A's course
    assert client.post(f"/archive/courses/{course_id}/restore", headers=auth(b)).status_code == 404
    assert client.delete(f"/archive/courses/{course_id}/permanent", headers=auth(b)).status_code == 404

    # Still sitting in A's archive afterward
    assert course_id in [c["id"] for c in client.get("/archive/courses", headers=auth(a)).json()]


def test_child_records_not_accessible_across_orgs(client, db_session, test_org, second_org):
    a = make_admin_in_org(client, test_org, "a_admin@test.com")
    b = make_admin_in_org(client, second_org, "b_admin@test.com")
    course_id = create_course_as(client, a)

    module_id = client.post(
        f"/courses/{course_id}/modules",
        json={"title": "Module 1", "content": "text", "order_index": 0},
        headers=auth(a)
    ).json()["id"]
    survey_id = client.post(
        f"/modules/{module_id}/surveys",
        json={"question": "How are you?", "survey_type": "open_response"},
        headers=auth(a)
    ).json()["id"]

    assert client.get(f"/modules/{module_id}", headers=auth(b)).status_code == 404
    assert client.post(
        f"/modules/{module_id}/surveys",
        json={"question": "Injected", "survey_type": "open_response"},
        headers=auth(b)
    ).status_code == 404
    assert client.post(f"/surveys/{survey_id}/answer", json={"answer_text": "hi"}, headers=auth(b)).status_code == 404
    assert client.get(f"/surveys/{survey_id}/responses", headers=auth(b)).status_code == 404
    assert client.delete(f"/surveys/{survey_id}", headers=auth(b)).status_code == 404

    # A can still reach everything
    assert client.get(f"/modules/{module_id}", headers=auth(a)).status_code == 200