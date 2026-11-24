import sqlite3

import pytest
from fastapi.testclient import TestClient

from auth import _hash_password
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


def test_signup_stores_full_name_and_keeps_legacy_payload_compatible(client):
    signup = client.post(
        "/api/auth/signup",
        json={
            "full_name": "  Asha Farmer  ",
            "email": "asha@example.com",
            "password": "secure-password",
        },
    )

    assert signup.status_code == 201
    assert signup.json()["user"]["full_name"] == "Asha Farmer"
    assert client.get("/api/auth/me").json()["user"]["full_name"] == "Asha Farmer"

    legacy_signup = client.post(
        "/api/auth/signup",
        json={"email": "legacy@example.com", "password": "secure-password"},
    )
    assert legacy_signup.status_code == 201
    assert legacy_signup.json()["user"]["full_name"] == ""


def test_signup_rejects_blank_full_name(client):
    response = client.post(
        "/api/auth/signup",
        json={
            "full_name": "  ",
            "email": "farmer@example.com",
            "password": "secure-password",
        },
    )
    assert response.status_code == 422


def test_existing_auth_database_keeps_accounts_after_name_migration(tmp_path, monkeypatch):
    database_path = tmp_path / "existing-auth.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """CREATE TABLE auth_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )"""
        )
        connection.execute(
            "INSERT INTO auth_users (email, password_hash, created_at) VALUES (?, ?, ?)",
            ("existing@example.com", _hash_password("secure-password"), 1),
        )

    monkeypatch.setenv("AUTH_DATABASE_PATH", str(database_path))
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login",
            json={"email": "existing@example.com", "password": "secure-password"},
        )

        assert login.status_code == 200
        assert login.json()["user"]["full_name"] == ""
        assert client.get("/api/auth/me").json()["user"]["email"] == "existing@example.com"
