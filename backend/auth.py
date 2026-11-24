"""Local email/password authentication for AgriMitra."""

import base64
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/api/auth", tags=["authentication"])

SESSION_COOKIE = "agrimitra_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7
PASSWORD_ITERATIONS = 310_000
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("Enter a valid email address.")
        return normalized


def _database_path() -> Path:
    configured_path = os.getenv("AUTH_DATABASE_PATH")
    path = Path(configured_path) if configured_path else Path(__file__).parent / "runtime" / "auth.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(_database_path(), timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


def _initialize_store() -> None:
    with _connect() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS auth_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS auth_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                signing_key BLOB NOT NULL
            )"""
        )
        connection.execute(
            "INSERT OR IGNORE INTO auth_settings (id, signing_key) VALUES (1, ?)",
            (secrets.token_bytes(32),),
        )


def _signing_key() -> bytes:
    _initialize_store()
    with _connect() as connection:
        row = connection.execute("SELECT signing_key FROM auth_settings WHERE id = 1").fetchone()
    if row is None:
        raise RuntimeError("Authentication signing key is not available.")
    return bytes(row["signing_key"])


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PASSWORD_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iteration_text, salt_text, digest_text = stored_hash.split("$", 3)
        iterations = int(iteration_text)
        if algorithm != "pbkdf2_sha256" or not 1 <= iterations <= 1_000_000:
            return False
        salt = base64.urlsafe_b64decode(salt_text)
        expected = base64.urlsafe_b64decode(digest_text)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _make_session(user_id: int) -> str:
    expires_at = int(time.time()) + SESSION_MAX_AGE
    payload = f"{user_id}.{expires_at}"
    signature = hmac.new(_signing_key(), payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def _read_session(token: str | None) -> dict | None:
    if not token:
        return None
    try:
        user_text, expires_text, signature = token.split(".", 2)
        payload = f"{user_text}.{expires_text}"
        expected = hmac.new(_signing_key(), payload.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected) or int(expires_text) <= int(time.time()):
            return None
        user_id = int(user_text)
    except (ValueError, UnicodeEncodeError):
        return None

    with _connect() as connection:
        row = connection.execute(
            "SELECT id, email FROM auth_users WHERE id = ?",
            (user_id,),
        ).fetchone()
    return {"id": row["id"], "email": row["email"]} if row else None


def _set_session_cookie(response: Response, user_id: int) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=_make_session(user_id),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=os.getenv("AUTH_COOKIE_SECURE", "false").strip().lower() == "true",
        samesite="lax",
        path="/",
    )


def _user_response(user: dict) -> dict:
    return {"id": user["id"], "email": user["email"]}


@router.post("/signup", status_code=201)
def signup(credentials: Credentials, response: Response) -> dict:
    _initialize_store()
    try:
        with _connect() as connection:
            cursor = connection.execute(
                "INSERT INTO auth_users (email, password_hash, created_at) VALUES (?, ?, ?)",
                (credentials.email, _hash_password(credentials.password), int(time.time())),
            )
            user_id = cursor.lastrowid
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="An account with this email already exists.") from error

    user = {"id": user_id, "email": credentials.email}
    _set_session_cookie(response, user_id)
    return {"user": _user_response(user)}


@router.post("/login")
def login(credentials: Credentials, response: Response) -> dict:
    _initialize_store()
    with _connect() as connection:
        row = connection.execute(
            "SELECT id, email, password_hash FROM auth_users WHERE email = ?",
            (credentials.email,),
        ).fetchone()

    if row is None or not _verify_password(credentials.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    user = {"id": row["id"], "email": row["email"]}
    _set_session_cookie(response, user["id"])
    return {"user": _user_response(user)}


@router.get("/me")
def current_user(request: Request) -> dict:
    user = _read_session(request.cookies.get(SESSION_COOKIE))
    if user is None:
        raise HTTPException(status_code=401, detail="Please log in to continue.")
    return {"user": _user_response(user)}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=os.getenv("AUTH_COOKIE_SECURE", "false").strip().lower() == "true",
        samesite="lax",
    )
    return {"message": "Logged out."}
