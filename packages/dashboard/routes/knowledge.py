from __future__ import annotations

from quart import Blueprint, request

from ..responses import err, ok


def create_blueprint() -> Blueprint:
    bp = Blueprint("knowledge", __name__, url_prefix="/api/v1/knowledge")

    @bp.route("/status", methods=["GET"])
    async def status():
        return ok({"available": False, "backend": None})

    @bp.route("", methods=["GET"])
    async def list_kbs():
        return ok([])

    @bp.route("", methods=["POST"])
    async def create_kb():
        return err("知识库尚未实现", 501)

    @bp.route("/<kb_id>", methods=["DELETE"])
    async def delete_kb(kb_id: str):
        return err("知识库尚未实现", 501)

    @bp.route("/<kb_id>/documents", methods=["GET"])
    async def list_documents(kb_id: str):
        return ok([])

    @bp.route("/<kb_id>/documents", methods=["POST"])
    async def upload_document(kb_id: str):
        _ = await request.get_data()
        return err("知识库尚未实现", 501)

    @bp.route("/<kb_id>/documents/<doc_id>", methods=["DELETE"])
    async def delete_document(kb_id: str, doc_id: str):
        return err("知识库尚未实现", 501)

    return bp
