from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.contrib.auth.models import User
from ninja.security import HttpBearer

from app.core.db import set_schema
from app.utils.constants import DEPT_SCHEMA_MAP

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_LIFETIME = timedelta(hours=1)
REFRESH_TOKEN_LIFETIME = timedelta(days=30)


def _encode(user_id: int, token_type: str, lifetime: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "type": token_type,
        "iat": now,
        "exp": now + lifetime,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=JWT_ALGORITHM)


def create_access_token(user_id: int) -> str:
    return _encode(user_id, "access", ACCESS_TOKEN_LIFETIME)


def create_refresh_token(user_id: int) -> str:
    return _encode(user_id, "refresh", REFRESH_TOKEN_LIFETIME)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[JWT_ALGORITHM])


def schema_for_user(user: User) -> str | None:
    if user.is_superuser:
        return DEPT_SCHEMA_MAP.get("진단검사의학과", "dlab")
    try:
        return DEPT_SCHEMA_MAP.get(user.profile.department)
    except Exception:
        return None


class JWTAuth(HttpBearer):
    def authenticate(self, request, token):
        try:
            payload = decode_token(token)
            if payload.get("type") != "access":
                return None
            user = User.objects.get(pk=payload["user_id"], is_active=True)
        except Exception:
            return None

        request.user = user
        set_schema(schema_for_user(user))
        return user
