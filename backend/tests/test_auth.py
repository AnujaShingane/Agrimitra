import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_DATABASE_PATH", str(tmp_path / "auth.sqlite3"))
    with TestClient(app) as test_client:
        yield test_client


def test_signup_login_current_user_and_logout(client):
    signup = client.post(
        "/api/auth/signup",
        json={"email": "Farmer@example.com", "password": "secure-password"},
    )

    assert signup.status_code == 201
    assert signup.json()["user"]["email"] == "farmer@example.com"
    assert client.cookies.get("agrimitra_session")
    assert client.get("/api/auth/me").json()["user"]["email"] == "farmer@example.com"

    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401

    login = client.post(
        "/api/auth/login",
        json={"email": "FARMER@example.com", "password": "secure-password"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["email"] == "farmer@example.com"


def test_signup_rejects_duplicate_accounts_and_login_rejects_wrong_password(client):
    credentials = {"email": "farmer@example.com", "password": "secure-password"}
    assert client.post("/api/auth/signup", json=credentials).status_code == 201
    assert client.post("/api/auth/signup", json=credentials).status_code == 409
    assert client.post(
        "/api/auth/login",
        json={"email": credentials["email"], "password": "wrong-password"},
    ).status_code == 401


def test_signup_validates_email_and_password(client):
    assert client.post(
        "/api/auth/signup",
        json={"email": "not-an-email", "password": "secure-password"},
    ).status_code == 422
    assert client.post(
        "/api/auth/signup",
        json={"email": "farmer@example.com", "password": "short"},
    ).status_code == 422
