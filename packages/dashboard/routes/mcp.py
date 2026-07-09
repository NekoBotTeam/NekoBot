from __future__ import annotations

from quart import Blueprint

from ..responses import err, ok


def create_blueprint() -> Blueprint:
    bp = Blueprint("mcp", __name__, url_prefix="/api/v1/mcp")

    @bp.route("", methods=["GET"])
    async def list_servers():
        return ok([])

    @bp.route("", methods=["POST"])
    async def add_server():
        return err("MCP 管理尚未实现", 501)

    @bp.route("/<name>", methods=["DELETE"])
    async def remove_server(name: str):
        return err("MCP 管理尚未实现", 501)

    @bp.route("/<name>/refresh", methods=["POST"])
    async def refresh_server(name: str):
        return err("MCP 管理尚未实现", 501)

    @bp.route("/refresh", methods=["POST"])
    async def refresh_all():
        return err("MCP 管理尚未实现", 501)

    return bp
