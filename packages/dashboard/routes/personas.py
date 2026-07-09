from __future__ import annotations

from quart import Blueprint, request

from ..managers.persona_manager import PersonaManager
from ..responses import err, ok


def create_blueprint(persona_manager: PersonaManager) -> Blueprint:
    bp = Blueprint("personas", __name__, url_prefix="/api/v1/personas")

    @bp.route("", methods=["GET"])
    async def list_personas():
        return ok(persona_manager.list())

    @bp.route("/<name>", methods=["GET"])
    async def get_persona(name: str):
        persona = persona_manager.get(name)
        if persona is None:
            return err("人格不存在", 404)
        return ok(persona)

    @bp.route("", methods=["POST"])
    async def create_persona():
        data = await request.get_json(silent=True) or {}
        name = str(data.get("name", ""))
        prompt = str(data.get("prompt", ""))
        if not name:
            return err("name 不能为空", 400)
        await persona_manager.create(name, prompt)
        return ok(message="人格已创建")

    @bp.route("/<name>", methods=["PUT"])
    async def update_persona(name: str):
        data = await request.get_json(silent=True) or {}
        prompt = str(data.get("prompt", ""))
        try:
            await persona_manager.update(name, prompt)
        except KeyError:
            return err("人格不存在", 404)
        return ok(message="人格已更新")

    @bp.route("/<name>", methods=["DELETE"])
    async def delete_persona(name: str):
        await persona_manager.delete(name)
        return ok(message="人格已删除")

    return bp
