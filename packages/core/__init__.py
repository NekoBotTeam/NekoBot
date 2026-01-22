"""NekoBot核心模块"""

__version__ = "1.0.0"

from .event_bus import event_bus, EventBus, EventPriority, on, on_any, emit, emit_sync
from .lifecycle import lifecycle, NekoBotLifecycle, get_lifecycle
from .database import DatabaseManager, db_manager
from .prompt_manager import PromptManager, prompt_manager
from .session_lock import SessionLockManager, session_lock_manager

# 配置管理器现在从 packages.config 导入
from ..config import get_config_manager, config as config_manager, ConfigManager

__all__ = [
    "__version__",
    # Event bus
    "event_bus",
    "EventBus",
    "EventPriority",
    "on",
    "on_any",
    "emit",
    "emit_sync",
    # Lifecycle
    "lifecycle",
    "NekoBotLifecycle",
    "get_lifecycle",
    # Database
    "DatabaseManager",
    "db_manager",
    # Prompt manager
    "PromptManager",
    "prompt_manager",
    # Session lock
    "SessionLockManager",
    "session_lock_manager",
    # Config manager
    "config_manager",
    "ConfigManager",
    "get_config_manager",
]
