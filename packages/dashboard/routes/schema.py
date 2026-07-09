from __future__ import annotations

from quart import Blueprint

from ..managers.schema_manager import SchemaManager
from ..responses import ok


def create_blueprint(schema_manager: SchemaManager) -> Blueprint:
    bp = Blueprint("schema", __name__, url_prefix="/api/v1/schema")

    @bp.route("/providers", methods=["GET"])
    async def provider_schemas():
        return ok(schema_manager.provider_schemas())

    @bp.route("/plugins/<name>", methods=["GET"])
    async def plugin_schema(name: str):
        return ok(schema_manager.plugin_schema(name))

    return bp
