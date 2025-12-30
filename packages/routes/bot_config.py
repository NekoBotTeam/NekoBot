"""机器人基础配置API

提供机器人基础配置的获取和更新功能
"""

import json
from pathlib import Path
from typing import Dict, Any
from loguru import logger

from .route import Route, Response, RouteContext
from ..core.config import load_config

CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "data" / "cmd_config.json"
PLATFORMS_SOURCES_PATH = Path(__file__).parent.parent.parent.parent / "data" / "platforms_sources.json"


class BotConfigRoute(Route):
    """机器人配置路由"""

    def __init__(self, context: RouteContext) -> None:
        super().__init__(context)
        self.config_path = CONFIG_PATH
        self.platforms_sources_path = PLATFORMS_SOURCES_PATH
        self.routes = [
            ("/api/bot/config", "GET", self.get_config),
            ("/api/bot/config", "POST", self.update_config),
        ]

    async def get_config(self) -> Dict[str, Any]:
        """获取机器人配置"""
        try:
            config = load_config()
            return Response().ok(data=config).to_dict()
        except Exception as e:
            logger.error(f"获取配置失败: {e}")
            return Response().error(f"获取配置失败: {str(e)}").to_dict()

    async def update_config(self) -> Dict[str, Any]:
        """更新机器人配置"""
        try:
            data = await self.get_request_data()
            if not data:
                return Response().error("缺少请求数据").to_dict()

            config = data.get("config")
            if not config or not isinstance(config, dict):
                return Response().error("配置数据格式错误").to_dict()

            current_config = load_config()

            base_allowed_keys = ["command_prefix", "server", "jwt", "webui_enabled", "demo"]
            platforms = config.get("platforms")

            if platforms is not None and isinstance(platforms, dict):
                self._save_platforms_sources(platforms)

            for key in config:
                if key in base_allowed_keys:
                    current_config[key] = config[key]

            self._save_config(current_config)
            return Response().ok(message="配置更新成功").to_dict()
        except Exception as e:
            logger.error(f"更新配置失败: {e}")
            return Response().error(f"更新配置失败: {str(e)}").to_dict()

    def _save_config(self, config: Dict[str, Any]) -> None:
        """保存配置到文件"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

    def _save_platforms_sources(self, platforms: Dict[str, Any]) -> None:
        """保存平台源配置到文件"""
        self.platforms_sources_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.platforms_sources_path, "w", encoding="utf-8") as f:
            json.dump(platforms, f, indent=2, ensure_ascii=False)
