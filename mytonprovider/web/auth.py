import base64
import hashlib
import hmac
import secrets
import time
from typing import Final

from fastapi import Request
from fastapi.responses import RedirectResponse
from nicegui import app
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from mytonprovider.database import WebDBSchema

SCRYPT_N: Final[int] = 2**14
SCRYPT_R: Final[int] = 8
SCRYPT_P: Final[int] = 1
SCRYPT_DKLEN: Final[int] = 64
SALT_BYTES: Final[int] = 16
SECRET_BYTES: Final[int] = 32

LOCKOUT_THRESHOLD: Final[int] = 5
LOCKOUT_DURATION_SEC: Final[int] = 15 * 60

PUBLIC_PATHS: Final[frozenset[str]] = frozenset({"/login"})
NICEGUI_PREFIX: Final[str] = "/_nicegui"


def hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
    )


def verify_password(password: str, salt_b64: str, expected_hash_b64: str) -> bool:
    try:
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(expected_hash_b64)
    except (ValueError, TypeError):
        return False
    actual = hash_password(password, salt)
    return hmac.compare_digest(actual, expected)


def generate_salt() -> str:
    return base64.b64encode(secrets.token_bytes(SALT_BYTES)).decode("ascii")


def generate_secret() -> str:
    return base64.b64encode(secrets.token_bytes(SECRET_BYTES)).decode("ascii")


def set_password(state: WebDBSchema, password: str) -> None:
    salt_b64 = generate_salt()
    salt = base64.b64decode(salt_b64)
    digest = hash_password(password, salt)
    state.password_salt = salt_b64
    state.password_hash = base64.b64encode(digest).decode("ascii")
    state.failed_attempts = 0
    state.lockout_until = 0


def is_locked_out(state: WebDBSchema, *, now: int | None = None) -> int:
    current = now if now is not None else int(time.time())
    if state.lockout_until and current < state.lockout_until:
        return state.lockout_until - current
    return 0


def register_failure(state: WebDBSchema, *, now: int | None = None) -> bool:
    current = now if now is not None else int(time.time())
    state.failed_attempts = (state.failed_attempts or 0) + 1
    if state.failed_attempts >= LOCKOUT_THRESHOLD:
        state.lockout_until = current + LOCKOUT_DURATION_SEC
        state.failed_attempts = 0
        return True
    return False


def register_success(state: WebDBSchema) -> None:
    state.failed_attempts = 0
    state.lockout_until = 0


def is_authenticated() -> bool:
    return bool(app.storage.user.get("authenticated"))


def login_session(*, username: str = "admin") -> None:
    app.storage.user.update(
        {"authenticated": True, "username": username, "login_at": int(time.time())}
    )


def logout_session() -> None:
    app.storage.user.clear()


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if path.startswith(NICEGUI_PREFIX) or path in PUBLIC_PATHS:
            return await call_next(request)
        if not is_authenticated():
            return RedirectResponse(f"/login?redirect_to={path}")
        return await call_next(request)
