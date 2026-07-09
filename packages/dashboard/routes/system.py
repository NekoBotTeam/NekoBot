from __future__ import annotations

from quart import Blueprint

from ..managers.config_store import ConfigStore
from ..managers.system_manager import SystemManager
from ..responses import ok


def create_blueprint(
    system_manager: SystemManager, config_store: ConfigStore
) -> Blueprint:
    bp = Blueprint("system", __name__, url_prefix="/api/v1/system")

    @bp.route("/info", methods=["GET"])
    async def info():
        return ok(system_manager.info())

    @bp.route("/reload-config", methods=["POST"])
    async def reload_config():
        config_store.reload()
        return ok(message="配置已重载")

    return bp
