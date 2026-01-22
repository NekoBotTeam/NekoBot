"""装饰器模块

提供错误处理、验证、认证等装饰器。
"""

from functools import wraps
from typing import Optional, List
from loguru import logger


def handle_route_errors(operation_name: str = "操作"):
    """路由错误处理装饰器

    Args:
        operation_name: 操作名称，用于错误消息

    Returns:
        装饰器函数
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            try:
                return await func(self, *args, **kwargs)
            except ValueError as e:
                logger.warning(f"{operation_name} 参数错误: {e}")
                return self.response.error(str(e)).to_dict()
            except Exception as e:
                logger.error(f"{operation_name} 失败: {e}", exc_info=True)
                return self.response.error(f"{operation_name}失败: {str(e)}").to_dict()

        return wrapper

    return decorator


def handle_async_errors(default_return=None, operation_name: str = "操作"):
    """异步错误处理装饰器

    Args:
        default_return: 错误时的默认返回值
        operation_name: 操作名称，用于日志

    Returns:
        装饰器函数
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"{operation_name} 失败: {e}", exc_info=True)
                return default_return

        return wrapper

    return decorator


def validate_request_data(
    required_fields: Optional[List[str]] = None, item_name: str = "项目"
):
    """验证请求数据的装饰器

    Args:
        required_fields: 必填字段列表
        item_name: 项目名称，用于错误消息

    Returns:
        装饰器函数
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            try:
                data = await self.get_request_data()
                if not data:
                    return self.response.error("缺少请求数据").to_dict()

                if required_fields:
                    is_valid, error_msg = await self.validate_required_fields(
                        data, required_fields
                    )
                    if not is_valid:
                        return self.response.error(error_msg).to_dict()

                result = await func(self, data, *args, **kwargs)
                return result
            except Exception as e:
                logger.error(f"{func.__name__} 失败: {e}", exc_info=True)
                return self.response.error(f"{func.__name__} 失败: {str(e)}").to_dict()

        return wrapper

    return decorator


def with_error_handling(item_name: str = "项目"):
    """通用错误处理装饰器，结合了请求验证和错误处理

    Args:
        item_name: 项目名称，用于错误消息

    Returns:
        装饰器函数
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            try:
                result = await func(self, *args, **kwargs)
                return result
            except ValueError as e:
                logger.warning(f"{item_name} 参数错误: {e}")
                return self.response.error(str(e)).to_dict()
            except Exception as e:
                logger.error(f"{item_name} 操作失败: {e}", exc_info=True)
                return self.response.error(f"{item_name}操作失败: {str(e)}").to_dict()

        return wrapper

    return decorator


def cache_result(ttl: int = 300):
    """缓存结果的装饰器

    Args:
        ttl: 缓存时间（秒）

    Returns:
        装饰器函数
    """

    cache = {}

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = (func.__name__, tuple(args), frozenset(kwargs.items()))
            if cache_key in cache:
                return cache[cache_key]

            result = await func(*args, **kwargs)
            cache[cache_key] = result
            return result

        return wrapper

    return decorator
