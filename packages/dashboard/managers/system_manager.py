from __future__ import annotations

import platform
import time
from typing import Any

import psutil

from ...app import NekoBotFramework


class SystemManager:
    """运行时系统信息（CPU/内存/计数）。"""

    def __init__(self, framework: NekoBotFramework) -> None:
        self.framework = framework
        self.start_time = time.time()

    def info(self) -> dict[str, Any]:
        process = psutil.Process()
        mem = process.memory_info()
        vm = psutil.virtual_memory()
        return {
            "python_version": platform.python_version(),
            "uptime_seconds": int(time.time() - self.start_time),
            "memory": {"rss_bytes": mem.rss, "vms_bytes": mem.vms},
            "cpu_percent": psutil.cpu_percent(),
            "system_memory": {
                "total": vm.total,
                "available": vm.available,
                "percent": vm.percent,
            },
            "plugins_loaded": len(self.framework.runtime_registry.plugins),
            "providers_loaded": len(self.framework.runtime_registry.providers),
        }
