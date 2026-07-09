from __future__ import annotations

import asyncio
from importlib.metadata import version as _pkg_version
from typing import Any

from hypercorn.asyncio import serve
from hypercorn.config import Config as HypercornConfig
from loguru import logger
from quart import Quart, g, jsonify, request

from ..app import NekoBotFramework
from .auth import AuthManager
from .config import DashboardConfig
from .managers import (
    ConfigStore,
    KnowledgeManager,
    LogManager,
    McpManager,
    PersonaManager,
    PlatformManager,
    PluginManager,
    ProviderManager,
    SchemaManager,
    SystemManager,
)
from .responses import err
from .routes import (
    auth_bp,
    knowledge_bp,
    logs_bp,
    mcp_bp,
    personas_bp,
    platforms_bp,
    plugins_bp,
    providers_bp,
    schema_bp,
    system_bp,
)
from .static import create_static_blueprint

_PUBLIC_PATHS = {"/", "/health", "/api/v1/ping", "/api/v1/auth/token"}


def _extract_token() -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    return request.args.get("api_key")


def _nekobot_version() -> str:
    try:
        return _pkg_version("nekobot")
    except Exception:
        return "0.1.0"


class DashboardApp:
    """总框架：组装 managers + 路由 + 鉴权 + 静态，并启动 hypercorn。"""

    def __init__(
        self,
        framework: NekoBotFramework,
        config_store: ConfigStore,
        dashboard_config: DashboardConfig | None = None,
    ) -> None:
        self.framework = framework
        self.config_store = config_store
        self.dashboard_config = dashboard_config or DashboardConfig()

        self.plugin_manager = PluginManager(
            framework, config_store, self.dashboard_config.plugins_dir
        )
        self.provider_manager = ProviderManager(config_store)
        self.schema_manager = SchemaManager(framework, self.plugin_manager)
        self.system_manager = SystemManager(framework)
        self.log_manager = LogManager(self.dashboard_config.logs_dir)
        self.platform_manager = PlatformManager(config_store)
        self.persona_manager = PersonaManager(config_store)
        self.mcp_manager = McpManager()
        self.knowledge_manager = KnowledgeManager()
        self.auth_manager = AuthManager(config_store)

        self.app = Quart("nekobot-dashboard", static_folder=None)
        self.app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024
        self._register()
        self._task: asyncio.Task[Any] | None = None

    def load_plugins(self) -> None:
        self.plugin_manager.load_all()

    def _register(self) -> None:
        app = self.app

        @app.before_request
        async def _auth_guard():
            path = request.path
            if path in _PUBLIC_PATHS or not path.startswith("/api/"):
                return None
            token = _extract_token()
            payload = self.auth_manager.decode(token) if token else None
            if not payload:
                return err("未授权", 401)
            g.user = payload
            return None

        @app.route("/api/v1/ping")
        async def ping():
            return jsonify(
                {
                    "status": "success",
                    "message": "pong",
                    "data": {"version": _nekobot_version()},
                }
            )

        app.register_blueprint(auth_bp(self.auth_manager))
        app.register_blueprint(plugins_bp(self.plugin_manager, self.config_store))
        app.register_blueprint(providers_bp(self.provider_manager))
        app.register_blueprint(schema_bp(self.schema_manager))
        app.register_blueprint(system_bp(self.system_manager, self.config_store))
        app.register_blueprint(logs_bp(self.log_manager))
        app.register_blueprint(platforms_bp(self.platform_manager))
        app.register_blueprint(personas_bp(self.persona_manager))
        app.register_blueprint(mcp_bp())
        app.register_blueprint(knowledge_bp())
        app.register_blueprint(create_static_blueprint(self.dashboard_config))

    async def start(self) -> None:
        cfg = HypercornConfig()
        cfg.bind = [f"{self.dashboard_config.host}:{self.dashboard_config.port}"]
        cfg.accesslog = None
        cfg.errorlog = None
        logger.info(
            "dashboard listening on http://{}:{}",
            self.dashboard_config.host,
            self.dashboard_config.port,
        )
        self._task = asyncio.create_task(serve(self.app, cfg))

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
