"""通用辅助函数

提供时间戳、UUID 等常用辅助函数。
"""

from datetime import datetime
import uuid


def get_current_timestamp() -> str:
    """获取当前 ISO 格式时间戳"""
    return datetime.now().isoformat()


def get_formatted_timestamp(format: str = "%Y-%m-%d %H:%M:%S") -> str:
    """获取格式化时间戳"""
    return datetime.now().strftime(format)


def generate_uuid() -> str:
    """生成 UUID 字符串"""
    return str(uuid.uuid4())
