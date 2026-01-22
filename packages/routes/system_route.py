"""系统信息API路由

提供系统资源监控信息
"""

from pathlib import Path
from typing import Dict, Any
from datetime import datetime
from loguru import logger
from quart import request

from .route import Route, Response, RouteContext
from packages.common import (
    JsonFileHandler,
    handle_route_errors,
)

# 系统信息缓存路径
SYSTEM_CACHE_PATH = (
    Path(__file__).parent.parent.parent.parent / "data" / "system_cache.json"
)


class SystemRoute(Route):
    """系统信息路由"""

    DEFAULT_CACHE_TTL = 60

    def __init__(self, context: RouteContext) -> None:
        super().__init__(context)
        self.json_handler = JsonFileHandler(SYSTEM_CACHE_PATH.parent)
        self.cache_filename = SYSTEM_CACHE_PATH.name
        self.routes = [
            ("/api/system/info", "GET", self.get_system_info),
            ("/api/system/webui/update", "POST", self.update_webui),
            ("/api/system/webui/version", "GET", self.get_webui_version),
            ("/api/system/cors/config", "GET", self.get_cors_config),
            ("/api/system/cors/update", "POST", self.update_cors_config),
        ]

    def _load_system_cache(self) -> Dict[str, Any]:
        """加载系统信息缓存"""
        default_cache = {"data": None, "cached_at": None, "ttl": self.DEFAULT_CACHE_TTL}
        return self.json_handler.load(self.cache_filename, default=default_cache)

    def _save_system_cache(
        self, data: Dict[str, Any], ttl: int = DEFAULT_CACHE_TTL
    ) -> None:
        """保存系统信息缓存"""
        cache = {
            "data": data,
            "cached_at": datetime.utcnow().isoformat(),
            "ttl": ttl,
        }
        self.json_handler.save(self.cache_filename, cache)

    def _is_cache_valid(self, cache: Dict[str, Any]) -> bool:
        """检查缓存是否有效"""
        if not cache.get("cached_at"):
            return False

        try:
            cached_at = datetime.fromisoformat(cache["cached_at"])
            ttl = cache.get("ttl", self.DEFAULT_CACHE_TTL)
            return (datetime.utcnow() - cached_at).total_seconds() < ttl
        except Exception:
            return False

    def _get_cpu_info(self) -> Dict[str, Any]:
        """获取CPU信息"""
        try:
            import psutil

            cpu_count = psutil.cpu_count(logical=True)
            cpu_physical = psutil.cpu_count(logical=False)
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_freq = psutil.cpu_freq()

            return {
                "usage": round(cpu_percent, 1),
                "cores": {
                    "logical": cpu_count,
                    "physical": cpu_physical,
                },
                "frequency": {
                    "current": round(cpu_freq.current, 2) if cpu_freq else None,
                    "min": round(cpu_freq.min, 2) if cpu_freq else None,
                    "max": round(cpu_freq.max, 2) if cpu_freq else None,
                },
            }
        except ImportError:
            logger.warning("psutil未安装，使用模拟CPU数据")
            return {
                "usage": 25.5,
                "cores": {"logical": 4, "physical": 2},
                "frequency": {"current": 2400.0, "min": 800.0, "max": 3200.0},
            }
        except Exception as e:
            logger.error(f"获取CPU信息失败: {e}")
            return {
                "usage": 0.0,
                "cores": {"logical": 0, "physical": 0},
                "frequency": {"current": None, "min": None, "max": None},
            }

    def _get_memory_info(self) -> Dict[str, Any]:
        """获取内存信息"""
        try:
            import psutil

            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()

            return {
                "total": memory.total,
                "total_gb": round(memory.total / (1024**3), 2),
                "used": memory.used,
                "used_gb": round(memory.used / (1024**3), 2),
                "available": memory.available,
                "available_gb": round(memory.available / (1024**3), 2),
                "percent": round(memory.percent, 1),
                "swap": {
                    "total": swap.total,
                    "total_gb": round(swap.total / (1024**3), 2),
                    "used": swap.used,
                    "used_gb": round(swap.used / (1024**3), 2),
                    "percent": round(swap.percent, 1),
                },
            }
        except ImportError:
            logger.warning("psutil未安装，使用模拟内存数据")
            return {
                "total": 17179869184,  # 16GB
                "total_gb": 16.0,
                "used": 8589934592,  # 8GB
                "used_gb": 8.0,
                "available": 8589934592,  # 8GB
                "available_gb": 8.0,
                "percent": 50.0,
                "swap": {
                    "total": 0,
                    "total_gb": 0.0,
                    "used": 0,
                    "used_gb": 0.0,
                    "percent": 0.0,
                },
            }
        except Exception as e:
            logger.error(f"获取内存信息失败: {e}")
            return {
                "total": 0,
                "total_gb": 0.0,
                "used": 0,
                "used_gb": 0.0,
                "available": 0,
                "available_gb": 0.0,
                "percent": 0.0,
                "swap": {
                    "total": 0,
                    "total_gb": 0.0,
                    "used": 0,
                    "used_gb": 0.0,
                    "percent": 0.0,
                },
            }

    def _get_disk_info(self) -> Dict[str, Any]:
        """获取磁盘信息"""
        try:
            import psutil

            # 获取根分区信息
            disk = psutil.disk_usage("/")
            disk_io = psutil.disk_io_counters()

            return {
                "total": disk.total,
                "total_gb": round(disk.total / (1024**3), 2),
                "used": disk.used,
                "used_gb": round(disk.used / (1024**3), 2),
                "free": disk.free,
                "free_gb": round(disk.free / (1024**3), 2),
                "percent": round((disk.used / disk.total) * 100, 1),
                "io": {
                    "read_bytes": disk_io.read_bytes if disk_io else 0,
                    "write_bytes": disk_io.write_bytes if disk_io else 0,
                    "read_count": disk_io.read_count if disk_io else 0,
                    "write_count": disk_io.write_count if disk_io else 0,
                },
            }
        except ImportError:
            logger.warning("psutil未安装，使用模拟磁盘数据")
            return {
                "total": 536870912000,  # 500GB
                "total_gb": 500.0,
                "used": 322122547200,  # 300GB
                "used_gb": 300.0,
                "free": 214748364800,  # 200GB
                "free_gb": 200.0,
                "percent": 60.0,
                "io": {
                    "read_bytes": 0,
                    "write_bytes": 0,
                    "read_count": 0,
                    "write_count": 0,
                },
            }
        except Exception as e:
            logger.error(f"获取磁盘信息失败: {e}")
            return {
                "total": 0,
                "total_gb": 0.0,
                "used": 0,
                "used_gb": 0.0,
                "free": 0,
                "free_gb": 0.0,
                "percent": 0.0,
                "io": {
                    "read_bytes": 0,
                    "write_bytes": 0,
                    "read_count": 0,
                    "write_count": 0,
                },
            }

    def _get_network_info(self) -> Dict[str, Any]:
        """获取网络信息"""
        try:
            import psutil

            net_io = psutil.net_io_counters()
            net_connections = len(psutil.net_connections())

            return {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv,
                "connections": net_connections,
            }
        except ImportError:
            logger.warning("psutil未安装，使用模拟网络数据")
            return {
                "bytes_sent": 0,
                "bytes_recv": 0,
                "packets_sent": 0,
                "packets_recv": 0,
                "connections": 0,
            }
        except Exception as e:
            logger.error(f"获取网络信息失败: {e}")
            return {
                "bytes_sent": 0,
                "bytes_recv": 0,
                "packets_sent": 0,
                "packets_recv": 0,
                "connections": 0,
            }

    def _get_process_info(self) -> Dict[str, Any]:
        """获取进程信息"""
        try:
            import psutil

            process = psutil.Process()
            return {
                "pid": process.pid,
                "name": process.name(),
                "status": process.status(),
                "create_time": datetime.fromtimestamp(
                    process.create_time()
                ).isoformat(),
                "cpu_percent": round(process.cpu_percent(interval=0.1), 1),
                "memory_info": {
                    "rss": process.memory_info().rss,
                    "rss_mb": round(process.memory_info().rss / (1024**2), 2),
                    "vms": process.memory_info().vms,
                    "vms_mb": round(process.memory_info().vms / (1024**2), 2),
                },
                "num_threads": process.num_threads(),
                "num_fds": process.num_fds() if hasattr(process, "num_fds") else 0,
            }
        except ImportError:
            logger.warning("psutil未安装，使用模拟进程数据")
            return {
                "pid": 12345,
                "name": "python",
                "status": "running",
                "create_time": datetime.utcnow().isoformat(),
                "cpu_percent": 5.2,
                "memory_info": {
                    "rss": 104857600,  # 100MB
                    "rss_mb": 100.0,
                    "vms": 524288000,  # 500MB
                    "vms_mb": 500.0,
                },
                "num_threads": 4,
                "num_fds": 32,
            }
        except Exception as e:
            logger.error(f"获取进程信息失败: {e}")
            return {
                "pid": 0,
                "name": "unknown",
                "status": "unknown",
                "create_time": None,
                "cpu_percent": 0.0,
                "memory_info": {
                    "rss": 0,
                    "rss_mb": 0.0,
                    "vms": 0,
                    "vms_mb": 0.0,
                },
                "num_threads": 0,
                "num_fds": 0,
            }

    async def get_system_info(self) -> Dict[str, Any]:
        """获取系统资源监控信息

        查询参数:
            use_cache: 是否使用缓存（默认true）

        返回:
            包含CPU、内存、磁盘、网络等系统信息的响应
        """
        try:
            # 获取查询参数
            use_cache = request.args.get("use_cache", "true").lower() == "true"

            # 检查缓存
            if use_cache:
                cache = self._load_system_cache()
                if self._is_cache_valid(cache):
                    logger.debug("使用缓存的系统信息")
                    return (
                        Response()
                        .ok(data=cache["data"], message="获取系统信息成功（缓存）")
                        .to_dict()
                    )

            # 获取系统信息
            cpu_info = self._get_cpu_info()
            memory_info = self._get_memory_info()
            disk_info = self._get_disk_info()
            network_info = self._get_network_info()
            process_info = self._get_process_info()

            # 构建系统信息
            system_info = {
                "cpu": cpu_info,
                "memory": memory_info,
                "disk": disk_info,
                "network": network_info,
                "process": process_info,
                "timestamp": datetime.utcnow().isoformat(),
            }

            # 保存缓存（60秒TTL）
            self._save_system_cache(system_info, ttl=60)

            return Response().ok(data=system_info, message="获取系统信息成功").to_dict()

        except Exception as e:
            logger.error(f"获取系统信息失败: {e}", exc_info=True)
            return Response().error(f"获取系统信息失败: {str(e)}").to_dict()

    async def get_webui_version(self) -> Dict[str, Any]:
        """获取当前 WebUI 版本"""
        try:
            from ..core.server import get_webui_version

            version = get_webui_version()
            return (
                Response()
                .ok(data={"version": version}, message="获取 WebUI 版本成功")
                .to_dict()
            )
        except Exception as e:
            logger.error(f"获取 WebUI 版本失败: {e}", exc_info=True)
            return Response().error(f"获取 WebUI 版本失败: {str(e)}").to_dict()

    async def update_webui(self) -> Dict[str, Any]:
        """更新 WebUI 到指定版本或最新版本

        请求体:
            version: 目标版本（可选，不指定则更新到最新版本）
            github_proxy: GitHub 代理地址（可选）

        返回:
            更新结果
        """
        try:
            data = await request.get_json() or {}
            version = data.get("version")
            github_proxy = data.get("github_proxy")

            from ..core.webui_manager import update_webui as webui_update

            logger.info(f"开始更新 WebUI，目标版本: {version or 'latest'}")
            success = await webui_update(custom_proxy=github_proxy, version=version)

            if success:
                from ..core.server import get_webui_version

                version = get_webui_version()
                return (
                    Response()
                    .ok(data={"version": version}, message="WebUI 更新成功")
                    .to_dict()
                )
            else:
                return Response().error("WebUI 更新失败，请检查日志").to_dict()
        except Exception as e:
            logger.error(f"更新 WebUI 失败: {e}", exc_info=True)
            return Response().error(f"更新 WebUI 失败: {str(e)}").to_dict()

    async def get_cors_config(self) -> Dict[str, Any]:
        """获取当前 CORS 配置"""
        try:
            cors_config = self.context.config.get("cors", {})
            return (
                Response().ok(data=cors_config, message="获取 CORS 配置成功").to_dict()
            )
        except Exception as e:
            logger.error(f"获取 CORS 配置失败: {e}", exc_info=True)
            return Response().error(f"获取 CORS 配置失败: {str(e)}").to_dict()

    @handle_route_errors("更新CORS配置")
    async def update_cors_config(self) -> Dict[str, Any]:
        """更新 CORS 配置

        请求体:
            allow_origin: 允许的跨域源
            allow_headers: 允许的请求头
            allow_methods: 允许的 HTTP 方法

        返回:
            更新结果
        """
        data = await request.get_json()

        if not data:
            return Response().error("请求体不能为空").to_dict()

        cors_config_path = (
            Path(__file__).parent.parent.parent.parent / "data" / "config.json"
        )

        cors_config = self.json_handler.load(
            cors_config_path.name,
            default={
                "allow_origin": "*",
                "allow_headers": ["Content-Type", "Authorization"],
                "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            },
        )

        if "allow_origin" in data:
            cors_config["allow_origin"] = data["allow_origin"]
        if "allow_headers" in data:
            cors_config["allow_headers"] = data["allow_headers"]
        if "allow_methods" in data:
            cors_config["allow_methods"] = data["allow_methods"]

        self.json_handler.save(cors_config_path.name, cors_config)

        logger.info(f"CORS 配置已更新: allow_origin={cors_config.get('allow_origin')}")

        return (
            Response()
            .ok(data=cors_config, message="CORS 配置更新成功，请重启服务以生效")
            .to_dict()
        )
