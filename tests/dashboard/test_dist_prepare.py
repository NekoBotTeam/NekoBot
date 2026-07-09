from __future__ import annotations

import zipfile
from pathlib import Path

from packages.dashboard.config import DashboardConfig
from packages.dashboard.static import ensure_dist_ready


def _make_zip(zip_path: Path, layout: str) -> None:
    """构造测试用 dist.zip。layout='flat' 平铺；'nested' 多一层 dist/。"""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w") as zf:
        if layout == "flat":
            zf.writestr("index.html", "<html>flat</html>")
            zf.writestr("assets/app.js", "console.log(1)")
        else:
            zf.writestr("dist/index.html", "<html>nested</html>")
            zf.writestr("dist/assets/app.js", "console.log(2)")


def test_ensure_dist_ready_extracts_flat_zip_when_index_missing(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    zip_path = tmp_path / "temp" / "dist.zip"
    _make_zip(zip_path, "flat")

    result = ensure_dist_ready(dist_dir, zip_path)

    assert result == dist_dir
    assert (dist_dir / "index.html").is_file()
    assert (dist_dir / "assets" / "app.js").is_file()


def test_ensure_dist_ready_flattens_zip_with_top_level_dist_dir(
    tmp_path: Path,
) -> None:
    dist_dir = tmp_path / "dist"
    zip_path = tmp_path / "temp" / "dist.zip"
    _make_zip(zip_path, "nested")

    result = ensure_dist_ready(dist_dir, zip_path)

    assert result == dist_dir
    # 必须摊平到 dist_dir/index.html，而不是 dist_dir/dist/index.html
    assert (dist_dir / "index.html").is_file()
    assert (dist_dir / "assets" / "app.js").is_file()
    assert not (dist_dir / "dist").exists()


def test_ensure_dist_ready_is_noop_when_index_already_present(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text("<html>existing</html>", encoding="utf-8")
    zip_path = tmp_path / "temp" / "dist.zip"
    _make_zip(zip_path, "flat")  # 即使有 zip 也不应触发解压

    result = ensure_dist_ready(dist_dir, zip_path)

    assert result == dist_dir
    existing = (dist_dir / "index.html").read_text(encoding="utf-8")
    assert existing == "<html>existing</html>"
    assert not (dist_dir / "assets").exists()


def test_ensure_dist_ready_returns_dir_without_raising_when_no_artifact(
    tmp_path: Path,
) -> None:
    dist_dir = tmp_path / "dist"
    zip_path = tmp_path / "temp" / "dist.zip"  # 故意不创建

    result = ensure_dist_ready(dist_dir, zip_path)

    assert result == dist_dir
    assert not (dist_dir / "index.html").exists()


def test_ensure_dist_ready_survives_corrupt_zip(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    zip_path = tmp_path / "temp" / "dist.zip"
    zip_path.parent.mkdir(parents=True)
    zip_path.write_bytes(b"not a real zip")  # 损坏的 zip

    result = ensure_dist_ready(dist_dir, zip_path)  # 不应抛异常

    assert result == dist_dir
    assert not (dist_dir / "index.html").exists()


def test_dashboard_config_dist_dir_reads_env_var(monkeypatch) -> None:
    monkeypatch.setenv("NEKOBOT_DIST_DIR", "/custom/dist/path")

    cfg = DashboardConfig()

    assert cfg.dist_dir == Path("/custom/dist/path")


def test_dashboard_config_dist_dir_defaults_when_env_unset(monkeypatch) -> None:
    monkeypatch.delenv("NEKOBOT_DIST_DIR", raising=False)

    cfg = DashboardConfig()

    assert cfg.dist_dir == Path("data/dist")
