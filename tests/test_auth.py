def test_claim_account_and_login(client):
    # First, create a player the normal way (as if an admin added them)
    # We need an admin to do this, so let's create one directly via the DB setup instead—
    # but for this first test, let's test something simpler: claiming an account that doesn't exist should fail cleanly

    response = client.post("/claim-account", json={
        "email": "nobody@example.com",
        "password": "testpassword123"
    })

    assert response.status_code == 404
    assert response.json()["detail"] == "No account found with this email"


def test_login_with_wrong_password_fails(client):
    response = client.post("/login", json={
        "email": "nobody@example.com",
        "password": "wrongpassword"
    })

    assert response.status_code == 401

def create_admin_directly(db_session):
    from database import TestingSessionLocal
    from auth import hash_password
    import models

    db = TestingSessionLocal()
    admin = models.User(
        name="Test Admin",
        jersey_number=0,
        position="staff",
        year=0,
        email="admin@test.com",
        password_hash=hash_password("adminpass123"),
        role="admin"
    )
    db.add(admin)
    db.commit()
    db.close()


def test_full_player_signup_flow(client, db_session):
    from tests.conftest import TestingSessionLocal
    from auth import hash_password
    import models

    # Set up an admin directly in the test database
    db = TestingSessionLocal()
    admin = models.User(
        name="Test Admin",
        jersey_number=0,
        position="staff",
        year=0,
        email="admin@test.com",
        password_hash=hash_password("adminpass123"),
        role="admin"
    )
    db.add(admin)
    db.commit()
    db.close()

    # Log in as admin
    login_response = client.post("/login", json={
        "email": "admin@test.com",
        "password": "adminpass123"
    })
    assert login_response.status_code == 200
    admin_token = login_response.json()["access_token"]

    # Admin creates a new player
    create_response = client.post(
        "/users",
        json={
            "name": "Test Player",
            "jersey_number": 23,
            "position": "QB",
            "year": 2,
            "email": "player@test.com",
            "role": "player"
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert create_response.status_code == 200

    # Player claims their account
    claim_response = client.post("/claim-account", json={
        "email": "player@test.com",
        "password": "playerpass123"
    })
    assert claim_response.status_code == 200
    assert "access_token" in claim_response.json()

    # Player logs in with their new password
    player_login = client.post("/login", json={
        "email": "player@test.com",
        "password": "playerpass123"
    })
    assert player_login.status_code == 200

    # A player should NOT be able to access the full roster
    player_token = player_login.json()["access_token"]
    roster_response = client.get(
        "/users",
        headers={"Authorization": f"Bearer {player_token}"}
    )
    assert roster_response.status_code == 403