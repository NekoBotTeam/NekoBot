from __future__ import annotations

from quart import Blueprint, request

from ..managers.config_store import ConfigStore
from ..managers.plugin_manager import PluginManager
from ..responses import err, ok


def create_blueprint(
    plugin_manager: PluginManager, config_store: ConfigStore
) -> Blueprint:
    bp = Blueprint("plugins", __name__, url_prefix="/api/v1/plugins")

    @bp.route("", methods=["GET"])
    async def list_plugins():
        infos = [plugin_manager.to_info(rp) for rp in plugin_manager.list_registered()]
        return ok(infos)

    @bp.route("/<name>", methods=["GET"])
    async def get_plugin(name: str):
        rp = plugin_manager.get_registered(name)
        if rp is None:
            return err("插件不存在", 404)
        return ok(plugin_manager.to_info(rp))

    @bp.route("/<name>/enabled", methods=["PATCH"])
    async def set_enabled(name: str):
        data = await request.get_json(silent=True) or {}
        await config_store.set_plugin_enabled(name, bool(data.get("enabled", True)))
        return ok(message="插件状态已更新")

    @bp.route("/<name>/reload", methods=["POST"])
    async def reload(name: str):
        plugin_manager.load_one(name)
        return ok(message="插件已重载")

    @bp.route("/<name>/config", methods=["GET"])
    async def get_config(name: str):
        return ok(config_store.get_plugin_config(name))

    @bp.route("/<name>/config", methods=["PUT"])
    async def put_config(name: str):
        data = await request.get_json(silent=True) or {}
        data.pop("config_id", None)
        await config_store.set_plugin_config(name, dict(data))
        return ok(message="插件配置已保存")

    return bp
