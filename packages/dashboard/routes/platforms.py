from __future__ import annotations

from quart import Blueprint, request

from ..managers.platform_manager import PlatformManager
from ..responses import err, ok


def create_blueprint(platform_manager: PlatformManager) -> Blueprint:
    bp = Blueprint("platforms", __name__, url_prefix="/api/v1/platforms")

    @bp.route("", methods=["GET"])
    async def list_platforms():
        return ok(platform_manager.list())

    @bp.route("", methods=["POST"])
    async def create_platform():
        data = await request.get_json(silent=True) or {}
        instance_uuid = str(data.get("instance_uuid", ""))
        data.pop("config_id", None)
        if not instance_uuid:
            return err("instance_uuid 不能为空", 400)
        await platform_manager.upsert(instance_uuid, dict(data))
        return ok(message="平台实例已创建")

    @bp.route("/<instance_uuid>", methods=["PUT"])
    async def update_platform(instance_uuid: str):
        data = await request.get_json(silent=True) or {}
        data.pop("config_id", None)
        await platform_manager.upsert(instance_uuid, dict(data))
        return ok(message="平台实例已更新")

    @bp.route("/<instance_uuid>", methods=["DELETE"])
    async def delete_platform(instance_uuid: str):
        await platform_manager.delete(instance_uuid)
        return ok(message="平台实例已删除")

    @bp.route("/<instance_uuid>/enabled", methods=["PATCH"])
    async def set_enabled(instance_uuid: str):
        data = await request.get_json(silent=True) or {}
        await platform_manager.set_enabled(
            instance_uuid, bool(data.get("enabled", True))
        )
        return ok(message="平台状态已更新")

    return bp
