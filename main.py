"""NekoBot 入口文件

启动基于 Quart 框架的 NekoBot 服务器
"""

import os
import sys

# 禁止生成 __pycache__ 目录
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from loguru import logger
import asyncio
import argparse
import getpass

# 导入统一的路径管理
from packages.core.utils import ensure_directories

logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> <level>[{level}]</level> {message}",
    level="DEBUG",
    colorize=True,
)


async def reset_password():
    """重置用户密码"""
    from packages.auth import reset_user_password

    print("请输入新密码：")
    password1 = getpass.getpass("密码: ")
    password2 = getpass.getpass("确认密码: ")

    if password1 != password2:
        logger.error("两次输入的密码不一致，重置失败")
        return 1

    if not password1:
        logger.error("密码不能为空，重置失败")
        return 1

    if reset_user_password("nekobot", password1):
        logger.info("密码已成功重置")
        return 0
    else:
        logger.error("密码重置失败")
        return 1


async def show_version():
    """显示版本信息"""
    from packages.core.server import get_full_version, NEKOBOT_VERSION

    version_info = get_full_version()
    print(f"NekoBot {NEKOBOT_VERSION}")
    print(f"{version_info}")
    return 0


async def show_help():
    """显示帮助信息"""
    help_text = """
NekoBot - 一个支持多聊天平台大模型的聊天机器人框架

用法:
    python main.py [命令] [选项]
    uv run main.py [命令] [选项]

可用命令:
    (默认)           启动 NekoBot 服务器
    reset-password    重置用户密码
    version, -v      显示版本信息
    help, -h         显示帮助信息

启动选项:
    -h, --help        显示帮助信息
    -v, --version     显示版本信息

示例:
    python main.py
    python main.py reset-password
    python main.py version
    uv run main.py

 更多信息:
     https://github.com/OfficialNekoTeam/NekoBot
"""
    print(help_text)
    return 0


async def check_env():
    """检查并初始化环境

    参考 AstrBot 的 check_env() 实现
    """
    import mimetypes

    # 检查 Python 版本
    if not (sys.version_info.major == 3 and sys.version_info.minor >= 10):
        logger.error("请使用 Python3.10+ 运行本项目。")
        sys.exit(1)

    # 确保必要的目录存在
    ensure_directories()

    # 针对问题 #181 的临时解决方案（参考 AstrBot）
    mimetypes.add_type("text/javascript", ".js")
    mimetypes.add_type("text/javascript", ".mjs")
    mimetypes.add_type("application/json", ".json")


async def main():
    """主函数：启动 NekoBot 服务器或执行命令行操作"""
    # 检查环境
    await check_env()

    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description="NekoBot 命令行工具",
        add_help=False,
        allow_abbrev=False,
    )
    parser.add_argument(
        "-h", "--help", action="store_true", dest="show_help", help="显示帮助信息"
    )
    parser.add_argument(
        "-v", "--version", action="store_true", dest="show_version", help="显示版本信息"
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["reset-password", "version", "help"],
        help="要执行的命令",
    )

    args = parser.parse_args()

    # 优先处理短选项
    if args.show_help:
        return await show_help()
    if args.show_version:
        return await show_version()

    # 处理子命令
    if args.command == "reset-password":
        return await reset_password()
    elif args.command == "version":
        return await show_version()
    elif args.command == "help":
        return await show_help()
    else:
        # 默认启动服务器
        logger.info("启动 NekoBot...")

        # 导入 Quart 应用
        from packages.app import run_app

        # 启动 Quart 应用
        await run_app()


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code if exit_code is not None else 0)
    except KeyboardInterrupt:
        logger.info("收到退出信号，正在关闭服务器...")
    except Exception as e:
        logger.error(f"操作失败: {e}")
        sys.exit(1)
