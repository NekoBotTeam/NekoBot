from __future__ import annotations

import asyncio
import os
import signal
import sys
from pathlib import Path

from loguru import logger

from packages.bootstrap import BootstrappedRuntime, bootstrap_runtime, load_app_config
from packages.dashboard import DashboardApp
from packages.dashboard.config import DashboardConfig
from packages.dashboard.managers import ConfigStore
from packages.dashboard.static import ensure_dist_ready


def _configure_logging() -> None:
    logger.remove()
    logger.add(
        sys.stdout,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> "
            "<level>[{level}]</level> {message}"
        ),
        level="INFO",
        colorize=True,
    )


async def async_main(
    config_path: str | None = None,
    *,
    run_forever: bool = True,
) -> BootstrappedRuntime:
    config = load_app_config(config_path)
    runtime = await bootstrap_runtime(config)

    config_store = ConfigStore(Path("data/config.json"))
    dashboard_config = DashboardConfig()
    dashboard = DashboardApp(runtime.framework, config_store, dashboard_config)
    dashboard.load_plugins()
    ensure_dist_ready(dashboard_config.dist_dir)
    await dashboard.start()

    if run_forever:
        # hypercorn serve() 会抢占 SIGINT，这里在它之后注册自己的 handler 覆盖回去，
        # 让 Ctrl+C 能正常触发关闭流程，而不是被吞掉。
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)
        await stop_event.wait()
        logger.info("收到退出信号，正在关闭...")
        try:
            await asyncio.wait_for(
                asyncio.gather(dashboard.stop(), runtime.stop()), timeout=3.0
            )
        except Exception:
            logger.warning("关闭超时或出错，强制退出")
            os._exit(0)

    return runtime


def main() -> None:
    _configure_logging()
    try:
        _ = asyncio.run(async_main())
    except KeyboardInterrupt:
        logger.info("收到退出信号，正在关闭...")


if __name__ == "__main__":
    main()
