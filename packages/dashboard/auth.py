from __future__ import annotations

import time
from collections.abc import Callable
from functools import wraps
from typing import Any

import jwt
from quart import g, request

from .responses import err

_DEFAULT_SECRET = "nekobot-insecure-default-secret"


class AuthManager:
    """JWT 签发与校验，凭证来自 config_store.auth_config。"""

    def __init__(self, config_store: Any) -> None:
        self.config_store = config_store

    def _auth_config(self) -> dict[str, Any]:
        return dict(self.config_store.get_auth_config())

    def verify_password(self, username: str, password: str) -> bool:
        cfg = self._auth_config()
        expected_user = str(cfg.get("username", ""))
        expected_pass = str(cfg.get("password", ""))
        return (
            username == expected_user
            and password == expected_pass
            and expected_pass != ""
        )

    def issue_token(self, username: str) -> str:
        cfg = self._auth_config()
        secret = str(cfg.get("jwt_secret", _DEFAULT_SECRET))
        now = int(time.time())
        payload = {
            "sub": username,
            "username": username,
            "iat": now,
            "exp": now + 7 * 24 * 3600,
        }
        return jwt.encode(payload, secret, algorithm="HS256")

    def decode(self, token: str) -> dict[str, Any] | None:
        cfg = self._auth_config()
        secret = str(cfg.get("jwt_secret", _DEFAULT_SECRET))
        try:
            payload = jwt.decode(token, secret, algorithms=["HS256"])
        except jwt.PyJWTError:
            return None
        return payload


def require_auth(auth: AuthManager) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """路由装饰器：校验 Authorization: Bearer <token> 或 ?api_key=。"""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            token: str | None = None
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
            if not token:
                token = request.args.get("api_key")
            if not token:
                return err("未授权", 401)
            payload = auth.decode(token)
            if not payload:
                return err("无效或过期的凭证", 401)
            g.user = payload
            return await fn(*args, **kwargs)

        return wrapper

    return decorator
