"""WebUI 管理模块

负责前端静态文件的检查、下载和更新
"""

import os
import zipfile
import asyncio
from typing import Optional, List
from loguru import logger
import aiohttp


# 项目根目录
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# 目录路径
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DIST_DIR = os.path.join(DATA_DIR, "dist")
TEMP_DIR = os.path.join(DATA_DIR, "temp")
DIST_ZIP_PATH = os.path.join(TEMP_DIR, "dist.zip")

# 版本文件
VERSION_FILE = os.path.join(DIST_DIR, "version")

# 仓库配置
DASHBOARD_REPO = "OfficialNekoTeam/Nekobot-Dashboard"

# GitHub 代理列表
GITHUB_PROXIES = [
    "https://ghproxy.com",
    "https://edgeone.gh-proxy.com",
    "https://hk.gh-proxy.com",
    "https://gh.llkk.cc",
]

# 直连标识
DIRECT_CONNECT = "direct"


class WebUIManager:
    """WebUI 管理器"""

    def __init__(
        self, custom_proxy: Optional[str] = None, version: Optional[str] = None
    ):
        self.custom_proxy = custom_proxy
        self.version = version
        self.session = aiohttp.ClientSession()

    async def close(self):
        """关闭会话"""
        await self.session.close()

    def _get_download_urls(self) -> List[str]:
        """获取下载 URL 列表

        Returns:
            URL 列表
        """
        base_url = f"https://github.com/{DASHBOARD_REPO}/releases"

        if self.version:
            download_path = f"/download/{self.version}/dist.zip"
        else:
            download_path = "/latest/download/dist.zip"

        urls = []

        # 添加自定义代理
        if (
            self.custom_proxy
            and self.custom_proxy not in GITHUB_PROXIES
            and self.custom_proxy != DIRECT_CONNECT
        ):
            urls.append(f"{self.custom_proxy}/{base_url}{download_path}")

        # 添加 GitHub 代理
        for proxy in GITHUB_PROXIES:
            urls.append(f"{proxy}/{base_url}{download_path}")

        # 添加直连
        urls.append(f"{base_url}{download_path}")

        return urls

    def _ensure_directories(self):
        """确保必要的目录存在"""
        os.makedirs(DIST_DIR, exist_ok=True)
        os.makedirs(TEMP_DIR, exist_ok=True)

    def _check_dist_exists(self) -> bool:
        """检查 dist 目录是否包含有效的静态文件

        Returns:
            是否存在有效的静态文件
        """
        index_path = os.path.join(DIST_DIR, "index.html")
        return os.path.exists(index_path)

    def _check_temp_dist_zip(self) -> bool:
        """检查 temp 目录是否存在 dist.zip

        Returns:
            是否存在 dist.zip
        """
        return os.path.exists(DIST_ZIP_PATH)

    async def _download_file(self, url: str) -> Optional[bytes]:
        """下载文件

        Args:
            url: 下载 URL

        Returns:
            文件内容，失败返回 None
        """
        try:
            timeout = aiohttp.ClientTimeout(total=300)
            async with self.session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    content = await response.read()
                    logger.info(f"成功从 {url} 下载 dist.zip ({len(content)} bytes)")
                    return content
                else:
                    logger.warning(f"从 {url} 下载失败: HTTP {response.status}")
        except asyncio.TimeoutError:
            logger.warning(f"从 {url} 下载超时")
        except Exception as e:
            logger.warning(f"从 {url} 下载时出错: {e}")
        return None

    def _extract_zip(self, zip_path: str, target_dir: str):
        """解压 zip 文件到目标目录

        Args:
            zip_path: zip 文件路径
            target_dir: 目标目录
        """
        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(target_dir)
            logger.info(f"成功解压 {zip_path} 到 {target_dir}")
        except Exception as e:
            logger.error(f"解压文件失败: {e}")
            raise

    def _cleanup_temp(self):
        """清理临时目录中的 dist.zip"""
        if os.path.exists(DIST_ZIP_PATH):
            try:
                os.remove(DIST_ZIP_PATH)
                logger.info(f"已清理临时文件 {DIST_ZIP_PATH}")
            except Exception as e:
                logger.warning(f"清理临时文件失败: {e}")

    async def _download_from_github(self) -> bool:
        """从 GitHub 下载前端文件

        Returns:
            是否下载成功
        """
        urls = self._get_download_urls()

        logger.info(f"尝试从 GitHub 下载前端文件，共 {len(urls)} 个源")

        for url in urls:
            logger.info(f"正在尝试从 {url.split('/')[2]} 下载...")

            content = await self._download_file(url)
            if content:
                try:
                    os.makedirs(TEMP_DIR, exist_ok=True)
                    with open(DIST_ZIP_PATH, "wb") as f:
                        f.write(content)

                    self._extract_zip(DIST_ZIP_PATH, DIST_DIR)

                    if self._check_dist_exists():
                        logger.info("前端文件下载并安装成功")

                        if self.version:
                            self._save_version(self.version)

                        self._cleanup_temp()
                        return True
                    else:
                        logger.warning("解压后未找到 index.html，文件可能损坏")
                        self._cleanup_temp()
                except Exception as e:
                    logger.error(f"处理下载的文件时出错: {e}")
                    self._cleanup_temp()

        logger.error("所有下载源均失败")
        return False

    def _save_version(self, version: str):
        """保存版本信息

        Args:
            version: 版本字符串
        """
        try:
            with open(VERSION_FILE, "w", encoding="utf-8") as f:
                f.write(version)
            logger.info(f"已保存 WebUI 版本: {version}")
        except Exception as e:
            logger.warning(f"保存版本信息失败: {e}")

    def get_version(self) -> str:
        """获取当前 WebUI 版本

        Returns:
            版本字符串，未找到返回 "unknown"
        """
        try:
            if os.path.exists(VERSION_FILE):
                with open(VERSION_FILE, "r", encoding="utf-8") as f:
                    return f.read().strip()
        except Exception as e:
            logger.warning(f"读取版本信息失败: {e}")
        return "unknown"

    async def initialize(self) -> bool:
        """初始化 WebUI

        按照以下顺序检查和获取前端文件：
        1. 检查 ./data/dist 是否包含 index.html
        2. 检查 ./data/temp 是否包含 dist.zip，如有则解压
        3. 从 GitHub 下载

        Returns:
            是否成功获取前端文件
        """
        self._ensure_directories()

        if self._check_dist_exists():
            version = self.get_version()
            logger.info(f"WebUI 已存在 (版本: {version})")
            return True

        logger.info("未找到前端静态文件，开始获取...")

        if self._check_temp_dist_zip():
            logger.info("找到预编译的 dist.zip，正在解压...")
            try:
                self._extract_zip(DIST_ZIP_PATH, DIST_DIR)
                if self._check_dist_exists():
                    logger.info("前端文件解压成功")
                    self._cleanup_temp()
                    return True
                else:
                    logger.warning("解压后未找到 index.html，文件可能损坏")
                    self._cleanup_temp()
            except Exception as e:
                logger.error(f"解压文件失败: {e}")
                self._cleanup_temp()

        return await self._download_from_github()

    async def update(self, version: Optional[str] = None) -> bool:
        """更新 WebUI 到指定版本或最新版本

        Args:
            version: 目标版本，None 表示最新版本

        Returns:
            是否更新成功
        """
        logger.info(f"开始更新 WebUI，目标版本: {version or 'latest'}")

        old_version = self.get_version()

        self.version = version

        success = await self._download_from_github()

        if success:
            new_version = self.get_version()
            logger.info(f"WebUI 更新成功: {old_version} -> {new_version}")
        else:
            logger.error("WebUI 更新失败")

        return success


async def initialize_webui(
    custom_proxy: Optional[str] = None, version: Optional[str] = None
) -> bool:
    """初始化 WebUI

    Args:
        custom_proxy: 自定义 GitHub 代理
        version: 指定版本，None 表示最新版本

    Returns:
        是否成功初始化
    """
    manager = WebUIManager(custom_proxy=custom_proxy, version=version)
    try:
        return await manager.initialize()
    finally:
        await manager.close()


async def update_webui(
    custom_proxy: Optional[str] = None, version: Optional[str] = None
) -> bool:
    """更新 WebUI

    Args:
        custom_proxy: 自定义 GitHub 代理
        version: 目标版本，None 表示最新版本

    Returns:
        是否成功更新
    """
    manager = WebUIManager(custom_proxy=custom_proxy, version=version)
    try:
        return await manager.update(version)
    finally:
        await manager.close()


def get_webui_version() -> str:
    """获取当前 WebUI 版本

    Returns:
        版本字符串
    """
    manager = WebUIManager()
    return manager.get_version()
