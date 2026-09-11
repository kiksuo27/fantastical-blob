from database import get_db
from tests.conftest import TestingSessionLocal
from auth import hash_password


def make_admin_and_login(client):
    db = TestingSessionLocal()
    import models
    admin = models.User(
        name="Test Admin",
        jersey_number=0,
        position="staff",
        year=0,
        email="scoreadmin@test.com",
        password_hash=hash_password("adminpass123"),
        role="admin"
    )
    db.add(admin)
    db.commit()
    db.close()

    login = client.post("/login", json={"email": "scoreadmin@test.com", "password": "adminpass123"})
    return login.json()["access_token"]


def make_player_and_login(client, admin_token, email="scoreplayer@test.com"):
    client.post(
        "/users",
        json={
            "name": "Test Player",
            "jersey_number": 10,
            "position": "WR",
            "year": 1,
            "email": email,
            "role": "player"
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    client.post("/claim-account", json={"email": email, "password": "playerpass123"})
    login = client.post("/login", json={"email": email, "password": "playerpass123"})
    return login.json()["access_token"]


def test_scoring_totals_only_count_scored_questions(client, db_session):
    admin_token = make_admin_and_login(client)
    player_token = make_player_and_login(client, admin_token)

    # Create an assessment
    assessment_response = client.post(
        "/assessments",
        json={"title": "Scoring Test", "is_public": True, "assessment_type": "player"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assessment_id = assessment_response.json()["id"]

    # Add a scored question worth 3 points
    q1 = client.post(
        f"/assessments/{assessment_id}/questions",
        json={"question_text": "Scored question", "question_type": "rating", "value_points": 3},
        headers={"Authorization": f"Bearer {admin_token}"}
    ).json()

    # Add an unscored question (no value_points)
    q2 = client.post(
        f"/assessments/{assessment_id}/questions",
        json={"question_text": "Unscored question", "question_type": "text"},
        headers={"Authorization": f"Bearer {admin_token}"}
    ).json()

    # Submit an attempt: full points on the scored question, plus an answer to the unscored one
    submit_response = client.post(
        f"/assessments/{assessment_id}/submit",
        json={
            "answers": [
                {"question_id": q1["id"], "answer_value": 3, "answer_text": None},
                {"question_id": q2["id"], "answer_value": None, "answer_text": "Some open response"}
            ]
        },
        headers={"Authorization": f"Bearer {player_token}"}
    )

    assert submit_response.status_code == 200
    result = submit_response.json()
    # Only the scored question's points should count — the unscored question contributes 0
    assert result["total_score"] == 3


def test_proficiency_band_boundaries(client, db_session):
    admin_token = make_admin_and_login(client)
    player_token = make_player_and_login(client, admin_token, email="bandplayer@test.com")

    assessment_response = client.post(
        "/assessments",
        json={"title": "Band Test", "is_public": True, "assessment_type": "player"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assessment_id = assessment_response.json()["id"]

    # One question worth up to 20 points, so we can hit exact boundary values directly
    question = client.post(
        f"/assessments/{assessment_id}/questions",
        json={"question_text": "Big question", "question_type": "rating", "value_points": 20},
        headers={"Authorization": f"Bearer {admin_token}"}
    ).json()

    # Test each boundary: 9 -> Not enough data, 10 -> Novice, 13 -> Intermediate, 16 -> Advanced, 18 -> Highly Advanced
    boundaries = [
        (9, "Not enough data"),
        (10, "Novice"),
        (13, "Intermediate"),
        (16, "Advanced"),
        (18, "Highly Advanced"),
    ]

    for score_value, expected_level in boundaries:
        response = client.post(
            f"/assessments/{assessment_id}/submit",
            json={"answers": [{"question_id": question["id"], "answer_value": score_value, "answer_text": None}]},
            headers={"Authorization": f"Bearer {player_token}"}
        )
        assert response.json()["level"] == expected_level, f"Score {score_value} should be {expected_level}"


def test_player_cannot_see_others_proficiency(client, db_session):
    admin_token = make_admin_and_login(client)
    player_token = make_player_and_login(client, admin_token, email="privacyplayer@test.com")

    # A player trying to check another user's proficiency should be blocked
    response = client.get(
        "/users/1/proficiency",
        headers={"Authorization": f"Bearer {player_token}"}
    )
    assert response.status_code == 403