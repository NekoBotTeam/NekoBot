from __future__ import annotations

from quart import Blueprint, g, request

from ..auth import AuthManager
from ..responses import err, ok


def create_blueprint(auth_manager: AuthManager) -> Blueprint:
    bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")

    @bp.route("/token", methods=["POST"])
    async def login():
        data = await request.get_json(silent=True) or {}
        username = str(data.get("username", ""))
        password = str(data.get("password", ""))
        if not auth_manager.verify_password(username, password):
            return err("用户名或密码错误", 401)
        token = auth_manager.issue_token(username)
        return ok({"access_token": token, "token_type": "bearer", "username": username})

    @bp.route("/me", methods=["GET"])
    async def me():
        user = getattr(g, "user", None) or {}
        return ok({"username": user.get("username", ""), "role": "admin"})

    @bp.route("/password", methods=["PUT"])
    async def change_password():
        user = getattr(g, "user", None) or {}
        username = user.get("username", "")
        data = await request.get_json(silent=True) or {}
        old_password = str(data.get("old_password", ""))
        new_password = str(data.get("new_password", ""))
        if not auth_manager.verify_password(username, old_password):
            return err("原密码错误", 400)
        if not new_password:
            return err("新密码不能为空", 400)
        auth_manager.config_store.raw.setdefault("auth_config", {})["password"] = (
            new_password
        )
        await auth_manager.config_store._write_back()  # noqa: SLF001
        return ok(message="密码已更新")

    return bp
