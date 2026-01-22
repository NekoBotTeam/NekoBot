"""JSON 文件处理器

提供统一的 JSON 文件读写操作。
"""

from pathlib import Path
from loguru import logger
import json


class JsonFileHandler:
    """JSON 文件处理器"""

    def __init__(self, base_path: Path):
        """初始化文件处理器

        Args:
            base_path: 基础路径
        """
        self.base_path = (
            Path(base_path) if not isinstance(base_path, Path) else base_path
        )

    def load(self, filename: str, default=None):
        """加载 JSON 文件

        Args:
            filename: 文件名
            default: 默认值

        Returns:
            解析后的数据或默认值
        """
        file_path = self.base_path / filename
        if not file_path.exists():
            return default

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载文件失败 {filename}: {e}")
            return default

    def save(
        self, filename: str, data, indent: int = 2, ensure_ascii: bool = False
    ) -> bool:
        """保存 JSON 文件

        Args:
            filename: 文件名
            data: 要保存的数据
            indent: 缩进空格数
            ensure_ascii: 是否确保 ASCII 编码

        Returns:
            是否保存成功
        """
        file_path = self.base_path / filename
        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
            return True
        except Exception as e:
            logger.error(f"保存文件失败 {filename}: {e}")
            return False

    def exists(self, filename: str) -> bool:
        """检查文件是否存在

        Args:
            filename: 文件名

        Returns:
            文件是否存在
        """
        return (self.base_path / filename).exists()

    def delete(self, filename: str) -> bool:
        """删除文件

        Args:
            filename: 文件名

        Returns:
            是否删除成功
        """
        file_path = self.base_path / filename
        try:
            if file_path.exists():
                file_path.unlink()
            return True
        except Exception as e:
            logger.error(f"删除文件失败 {filename}: {e}")
            return False
