import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
from main import app

TEST_DATABASE_URL = "postgresql://localhost/test_db"

engine = create_engine(TEST_DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function")
def db_session():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    return TestClient(app)

@pytest.fixture()
def test_org(db_session):
    db = TestingSessionLocal()
    import models
    org = models.Organization(name="Test Org", plan="single_team")
    db.add(org)
    db.commit()
    db.refresh(org)
    org_id = org.id
    db.close()
    return org_id

@pytest.fixture()
def second_org(db_session):
    db = TestingSessionLocal()
    import models
    org = models.Organization(name="Second Test Org", plan="single_team")
    db.add(org)
    db.commit()
    db.refresh(org)
    org_id = org.id
    db.close()
    return org_id