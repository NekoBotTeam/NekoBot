from .auth import create_blueprint as auth_bp
from .knowledge import create_blueprint as knowledge_bp
from .logs import create_blueprint as logs_bp
from .mcp import create_blueprint as mcp_bp
from .personas import create_blueprint as personas_bp
from .platforms import create_blueprint as platforms_bp
from .plugins import create_blueprint as plugins_bp
from .providers import create_blueprint as providers_bp
from .schema import create_blueprint as schema_bp
from .system import create_blueprint as system_bp

__all__ = [
    "auth_bp",
    "knowledge_bp",
    "logs_bp",
    "mcp_bp",
    "personas_bp",
    "platforms_bp",
    "plugins_bp",
    "providers_bp",
    "schema_bp",
    "system_bp",
]
