from tests.conftest import TestingSessionLocal
from auth import hash_password
import models


def make_admin_and_login(client):
    db = TestingSessionLocal()
    admin = models.User(
        name="Course Test Admin",
        jersey_number=0,
        position="staff",
        year=0,
        email="courseadmin@test.com",
        password_hash=hash_password("adminpass123"),
        role="admin"
    )
    db.add(admin)
    db.commit()
    db.close()

    login = client.post("/login", json={"email": "courseadmin@test.com", "password": "adminpass123"})
    return login.json()["access_token"]


def test_admin_can_delete_and_restore_course(client, db_session):
    admin_token = make_admin_and_login(client)

    create_response = client.post(
        "/courses",
        json={"title": "Test Course", "is_public": True},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert create_response.status_code == 200
    course_id = create_response.json()["id"]

    # Deleting should succeed, not 404 — this is the exact bug we just fixed
    delete_response = client.delete(
        f"/courses/{course_id}",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert delete_response.status_code == 200

    # A deleted course should no longer appear in the normal course list
    list_response = client.get(
        "/courses",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    course_ids = [c["id"] for c in list_response.json()]
    assert course_id not in course_ids

    # It should appear in the archive
    archive_response = client.get(
        "/archive/courses",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    archived_ids = [c["id"] for c in archive_response.json()]
    assert course_id in archived_ids

    # Restoring it should bring it back
    restore_response = client.post(
        f"/archive/courses/{course_id}/restore",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert restore_response.status_code == 200

    list_response_after = client.get(
        "/courses",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    course_ids_after = [c["id"] for c in list_response_after.json()]
    assert course_id in course_ids_after