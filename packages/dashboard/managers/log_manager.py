from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger


class LogManager:
    """读取 data/logs 下的日志文件并按行返回尾部。"""

    def __init__(self, logs_dir: Path | None = None) -> None:
        self.logs_dir = Path(logs_dir) if logs_dir is not None else Path("data/logs")

    def list_files(self) -> list[dict[str, Any]]:
        if not self.logs_dir.exists():
            return []
        result: list[dict[str, Any]] = []
        for entry in sorted(self.logs_dir.glob("*.log*")):
            try:
                stat = entry.stat()
            except OSError:
                continue
            result.append(
                {
                    "name": entry.name,
                    "size_bytes": stat.st_size,
                    "modified_at": int(stat.st_mtime),
                }
            )
        return result

    def tail(self, filename: str, lines: int = 200) -> list[str]:
        base = self.logs_dir.resolve()
        target = (self.logs_dir / filename).resolve()
        try:
            target.relative_to(base)
        except ValueError:
            logger.warning("log path escapes logs dir: {}", filename)
            return []
        if not target.is_file():
            return []
        text = target.read_text(encoding="utf-8", errors="replace")
        all_lines = text.splitlines()
        return all_lines[-lines:] if lines > 0 else all_lines
