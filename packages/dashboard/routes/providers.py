from __future__ import annotations

from quart import Blueprint, request

from ..managers.provider_manager import ProviderManager
from ..responses import err, ok


def create_blueprint(provider_manager: ProviderManager) -> Blueprint:
    bp = Blueprint("providers", __name__, url_prefix="/api/v1/providers")

    @bp.route("", methods=["GET"])
    async def list_providers():
        return ok(provider_manager.list())

    @bp.route("/<name>", methods=["GET"])
    async def get_provider(name: str):
        cfg = provider_manager.get(name)
        if cfg is None:
            return err("提供商不存在", 404)
        return ok({name: cfg})

    @bp.route("", methods=["POST"])
    async def create_provider():
        data = await request.get_json(silent=True) or {}
        name = str(data.pop("name", ""))
        data.pop("config_id", None)
        if not name:
            return err("name 不能为空", 400)
        await provider_manager.upsert(name, dict(data))
        return ok(message="提供商已创建")

    @bp.route("/<name>", methods=["PUT"])
    async def update_provider(name: str):
        data = await request.get_json(silent=True) or {}
        data.pop("config_id", None)
        await provider_manager.upsert(name, dict(data))
        return ok(message="提供商已更新")

    @bp.route("/<name>", methods=["DELETE"])
    async def delete_provider(name: str):
        await provider_manager.delete(name)
        return ok(message="提供商已删除")

    @bp.route("/<name>/enabled", methods=["PATCH"])
    async def set_enabled(name: str):
        data = await request.get_json(silent=True) or {}
        await provider_manager.set_enabled(name, bool(data.get("enabled", True)))
        return ok(message="提供商状态已更新")

    return bp
