from __future__ import annotations

from quart import Blueprint, request

from ..managers.log_manager import LogManager
from ..responses import ok


def create_blueprint(log_manager: LogManager) -> Blueprint:
    bp = Blueprint("logs", __name__, url_prefix="/api/v1/logs")

    @bp.route("", methods=["GET"])
    async def list_logs():
        return ok(log_manager.list_files())

    @bp.route("/<path:filename>", methods=["GET"])
    async def tail(filename: str):
        lines_raw = request.args.get("lines", "200")
        try:
            line_count = int(lines_raw)
        except ValueError:
            line_count = 200
        return ok(log_manager.tail(filename, line_count))

    return bp
