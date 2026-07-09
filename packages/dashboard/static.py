from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path

from loguru import logger
from quart import Blueprint, jsonify, send_from_directory

from .config import DashboardConfig

DIST_ZIP_PATH = Path("data/temp/dist.zip")
"""前端产物约定路径：部署方经 data 卷放入 ./data/temp/dist.zip，由后端运行时解压。"""


def ensure_dist_ready(dist_dir: Path, zip_path: Path = DIST_ZIP_PATH) -> Path:
    """确保 dist_dir 下有可托管的前端产物，返回最终的 dist_dir。

    1. dist_dir/index.html 已存在 → 直接返回（幂等，兼容本地 data/dist 软链）。
    2. 存在 zip_path → 解压到 dist_dir（兼容平铺/嵌套布局），失败仅告警不抛。
    3. 都没有 → 告警返回；静态蓝图会优雅 404，不阻断 bot 启动。
    """
    if (dist_dir / "index.html").is_file():
        return dist_dir

    if zip_path.is_file():
        try:
            _extract_dist_zip(zip_path, dist_dir)
            logger.info("已从前端产物 {} 解压到 {}", zip_path, dist_dir)
        except Exception as exc:  # 解压失败不应阻断启动
            logger.warning("解压前端产物 {} 失败：{}", zip_path, exc)
        return dist_dir

    logger.warning(
        "未找到前端产物（{} 与 {} 均无 index.html），dashboard 将返回 404",
        dist_dir,
        zip_path,
    )
    return dist_dir


def _extract_dist_zip(zip_path: Path, dist_dir: Path) -> None:
    """解压 zip 到 dist_dir，自动适配「平铺」或「多一层 dist/」两种内部布局。"""
    dist_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        web_root = Path(tmp)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(web_root)
        web_root = _locate_web_root(web_root)
        # 先快照再移动，避免边遍历边删导致迭代异常
        for entry in list(web_root.iterdir()):
            target = dist_dir / entry.name
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
            shutil.move(str(entry), str(target))


def _locate_web_root(base: Path) -> Path:
    """定位直接含 index.html 的目录：优先 base 本身，其次一级子目录，否则回退 base。"""
    if (base / "index.html").is_file():
        return base
    for child in base.iterdir():
        if child.is_dir() and (child / "index.html").is_file():
            return child
    return base


def create_static_blueprint(config: DashboardConfig) -> Blueprint:
    """前端静态资源反代 + SPA fallback + /health。"""
    bp = Blueprint("dashboard_static", __name__)
    dist = config.dist_dir

    @bp.route("/health")
    async def health():
        return jsonify({"status": "ok"})

    @bp.route("/")
    async def index_root():
        if (dist / "index.html").is_file():
            return await send_from_directory(dist, "index.html")
        return jsonify({"message": "dashboard dist not built"}), 404

    @bp.route("/<path:path>")
    async def assets(path: str):
        if path.startswith("api/"):
            return jsonify({"success": False, "message": "not found"}), 404
        if (dist / path).is_file():
            return await send_from_directory(dist, path)
        if (dist / "index.html").is_file():
            return await send_from_directory(dist, "index.html")
        return jsonify({"message": "dashboard dist not built"}), 404

    return bp
