"""更多设置API

提供系统设置、重启服务、检查更新等功能
"""

from pathlib import Path
from typing import Dict, Any
from loguru import logger

from .route import Route, Response, RouteContext
from ..config import load_config
from packages.common import (
    JsonFileHandler,
    handle_route_errors,
)

SETTINGS_PATH = Path(__file__).parent.parent.parent.parent / "data" / "settings.json"


class SettingsRoute(Route):
    """更多设置路由"""

    DEFAULT_SETTINGS = {
        "theme": "dark",
        "language": "zh-CN",
        "notifications": {"enabled": True, "types": ["error", "warning"]},
        "auto_restart": False,
    }

    ALLOWED_SETTINGS_KEYS = ["theme", "language", "notifications", "auto_restart"]

    def __init__(self, context: RouteContext) -> None:
        super().__init__(context)
        self.json_handler = JsonFileHandler(SETTINGS_PATH.parent)
        self.settings_filename = SETTINGS_PATH.name
        self.routes = [
            ("/api/settings", "GET", self.get_settings),
            ("/api/settings", "POST", self.update_settings),
            ("/api/settings/restart", "POST", self.restart_service),
            ("/api/settings/update", "GET", self.check_update),
        ]

    @handle_route_errors("获取系统设置")
    async def get_settings(self) -> Dict[str, Any]:
        """获取系统设置"""
        settings = self.json_handler.load(
            self.settings_filename, default=self.DEFAULT_SETTINGS
        )
        config = load_config()
        return Response().ok(data={"settings": settings, "config": config}).to_dict()

    @handle_route_errors("更新系统设置")
    async def update_settings(self) -> Dict[str, Any]:
        """更新系统设置"""
        data = await self.get_request_data()
        if not data:
            return Response().error("缺少请求数据").to_dict()

        settings = data.get("settings")
        if not settings or not isinstance(settings, dict):
            return Response().error("设置数据格式错误").to_dict()

        current_settings = self.json_handler.load(
            self.settings_filename, default=self.DEFAULT_SETTINGS
        )
        for key in settings:
            if key in self.ALLOWED_SETTINGS_KEYS:
                current_settings[key] = settings[key]

        self.json_handler.save(self.settings_filename, current_settings)
        return Response().ok(message="设置更新成功").to_dict()

    @handle_route_errors("重启服务")
    async def restart_service(self) -> Dict[str, Any]:
        """重启服务"""
        if self.context.config.get("demo", False):
            return Response().error("Demo模式下不允许重启服务").to_dict()

        logger.info("收到重启服务请求")
        return Response().ok(message="服务重启指令已发送").to_dict()

    @handle_route_errors("检查更新")
    async def check_update(self) -> Dict[str, Any]:
        """检查更新"""
        from tomli import load as load_toml

        pyproject_path = Path(__file__).parent.parent.parent.parent / "pyproject.toml"
        if not pyproject_path.exists():
            return Response().error("无法找到pyproject.toml文件").to_dict()

        with open(pyproject_path, "rb") as f:
            pyproject = load_toml(f)

        current_version = pyproject.get("project", {}).get("version", "unknown")
        return (
            Response()
            .ok(
                data={
                    "current_version": current_version,
                    "has_update": False,
                    "latest_version": current_version,
                    "update_url": "",
                }
            )
            .to_dict()
        )
