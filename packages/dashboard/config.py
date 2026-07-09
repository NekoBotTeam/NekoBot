from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DashboardConfig:
    host: str = "0.0.0.0"
    port: int = 6285
    dist_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("NEKOBOT_DIST_DIR", "data/dist"))
    )
    jwt_algorithm: str = "HS256"
    jwt_exp_seconds: int = 7 * 24 * 3600
    plugins_dir: Path = Path("data/plugins")
    logs_dir: Path = Path("data/logs")
