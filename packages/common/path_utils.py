"""路径工具函数

提供路径操作的辅助函数。
"""

from pathlib import Path


def ensure_path(path: Path) -> Path:
    """确保路径的父目录存在

    Args:
        path: 路径

    Returns:
        规范化后的路径对象
    """
    if not isinstance(path, Path):
        path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def ensure_dir(directory: Path) -> Path:
    """确保目录存在

    Args:
        directory: 目录路径

    Returns:
        规范化后的目录路径对象
    """
    if not isinstance(directory, Path):
        directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    return directory
