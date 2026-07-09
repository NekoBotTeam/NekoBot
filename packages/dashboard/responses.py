from __future__ import annotations

from typing import Any

from quart import jsonify


def ok(data: Any = None, message: str = "success"):
    """成功响应信封 {success, status, message, data}，兼容前端拦截器。"""
    return jsonify(
        {"success": True, "status": "success", "message": message, "data": data}
    )


def err(message: str = "error", status: int = 400, data: Any = None):
    """失败响应信封。返回 (response, status_code)。"""
    return (
        jsonify(
            {"success": False, "status": "error", "message": message, "data": data}
        ),
        status,
    )
