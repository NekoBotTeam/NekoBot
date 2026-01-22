"""LLM Token 计数器

参考 AstrBot 实现，提供精确的 token 计数功能
支持多种计数策略和后端
"""

import re
from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Dict, Any
from loguru import logger


class TokenCounterBackend(Enum):
    """Token 计数器后端类型"""
    ESTIMATE = "estimate"        # 简单估算（最快）
    TIKTOKEN = "tiktoken"         # tiktoken 库（精确）
    CL100K_BASE = "cl100k_base"   # GPT-4/GPT-3.5 编码器
    O200K_BASE = "o200k_base"     # GPT-4-turbo 编码器


class BaseTokenCounter(ABC):
    """Token 计数器基类"""

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """计算文本的 token 数量

        Args:
            text: 要计算的文本

        Returns:
            token 数量
        """
        pass

    @abstractmethod
    def count_messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """计算消息列表的 token 数量

        Args:
            messages: 消息列表

        Returns:
            token 数量
        """
        pass


class EstimateTokenCounter(BaseTokenCounter):
    """估算型 Token 计数器（最快，但不精确）

    适用于快速检查和开发调试
    """

    # 中文字符范围
    CHINESE_PATTERN = re.compile(r"[\u4e00-\u9fff]")
    # 英文单词模式
    WORD_PATTERN = re.compile(r"\b\w+\b")

    def __init__(self, chinese_ratio: float = 1.5, english_ratio: float = 1.0):
        """初始化估算计数器

        Args:
            chinese_ratio: 中文字符 token 比例
            english_ratio: 英文单词 token 比例
        """
        self.chinese_ratio = chinese_ratio
        self.english_ratio = english_ratio

    def count_tokens(self, text: str) -> int:
        """估算文本的 token 数量"""
        # 统计中文字符
        chinese_chars = len(self.CHINESE_PATTERN.findall(text))
        # 统计英文单词
        english_words = len(self.WORD_PATTERN.findall(text))
        # 其他字符（标点、数字等）
        other_chars = len(text) - chinese_chars - sum(len(m) for m in self.WORD_PATTERN.findall(text))

        return int(
            chinese_chars * self.chinese_ratio +
            english_words * self.english_ratio +
            other_chars * 0.5
        )

    def count_messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """估算消息列表的 token 数量"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            # 消息格式开销
            total += 4  # 每条消息大约 4 个 token 的格式开销
            total += self.count_tokens(content)
        return total


class TikTokenCounter(BaseTokenCounter):
    """基于 tiktoken 的精确 Token 计数器

    使用 OpenAI 的官方编码器进行精确计数
    """

    def __init__(self, encoding_name: str = "cl100k_base"):
        """初始化 tiktoken 计数器

        Args:
            encoding_name: 编码器名称
                - cl100k_base: GPT-4, GPT-3.5-turbo, GPT-4-turbo
                - o200k_base: GPT-4o, GPT-4o-mini
        """
        self.encoding_name = encoding_name
        self._encoding = None
        self._init_encoding()

    def _init_encoding(self) -> None:
        """初始化编码器"""
        try:
            import tiktoken
            self._encoding = tiktoken.get_encoding(self.encoding_name)
            logger.debug(f"使用 tiktoken 编码器: {self.encoding_name}")
        except ImportError:
            logger.warning("tiktoken 未安装，回退到估算模式")
            self._encoding = None
        except Exception as e:
            logger.error(f"初始化 tiktoken 失败: {e}，回退到估算模式")
            self._encoding = None

    def count_tokens(self, text: str) -> int:
        """计算文本的 token 数量"""
        if self._encoding is None:
            # 回退到估算
            return EstimateTokenCounter().count_tokens(text)

        try:
            tokens = self._encoding.encode(text)
            return len(tokens)
        except Exception as e:
            logger.error(f"tiktoken 计数失败: {e}，回退到估算")
            return EstimateTokenCounter().count_tokens(text)

    def count_messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """计算消息列表的 token 数量

        参考 OpenAI 的计算方式：
        - 每条消息: <im_start>{role/name}\n{content}<im_end>\n
        - 每条消息大约 4 个 token 的格式开销
        - 名称和角色也占用 token
        """
        if self._encoding is None:
            return EstimateTokenCounter().count_messages_tokens(messages)

        try:
            # 计算每条消息的 token 数
            num_tokens = 0
            for message in messages:
                # 消息格式开销
                num_tokens += 4  # 每条消息的格式开销

                # 角色和名称
                role = message.get("role", "")
                name = message.get("name", "")

                num_tokens += len(self._encoding.encode(role))
                if name:
                    num_tokens += len(self._encoding.encode(name))

                # 内容
                content = message.get("content", "")
                if isinstance(content, str):
                    num_tokens += len(self._encoding.encode(content))
                elif isinstance(content, list):
                    # 多模态内容
                    for item in content:
                        if isinstance(item, dict):
                            item_type = item.get("type", "")
                            if item_type == "text":
                                text = item.get("text", "")
                                num_tokens += len(self._encoding.encode(text))
                            elif item_type == "image_url":
                                # 图片 token 估算（简化）
                                num_tokens += 85  # 低分辨率图片约 85 tokens

            # 每个 reply 的格式开销
            num_tokens += 3  # <im_start>assistant

            return num_tokens

        except Exception as e:
            logger.error(f"tiktoken 消息计数失败: {e}，回退到估算")
            return EstimateTokenCounter().count_messages_tokens(messages)


class CachedTokenCounter(BaseTokenCounter):
    """带缓存的 Token 计数器

    缓存常见文本的 token 计数结果，提高性能
    """

    def __init__(self, base_counter: BaseTokenCounter, cache_size: int = 1000):
        """初始化缓存计数器

        Args:
            base_counter: 底层计数器
            cache_size: 缓存大小
        """
        self.base_counter = base_counter
        self._text_cache: Dict[str, int] = {}
        self._cache_size = cache_size
        self._hit_count = 0
        self._miss_count = 0

    def count_tokens(self, text: str) -> int:
        """计算文本的 token 数量（带缓存）"""
        # 检查缓存
        if text in self._text_cache:
            self._hit_count += 1
            return self._text_cache[text]

        # 缓存未命中
        self._miss_count += 1
        result = self.base_counter.count_tokens(text)

        # 更新缓存（LRU 简化实现）
        if len(self._text_cache) >= self._cache_size:
            # 删除最旧的条目（第一个）
            oldest = next(iter(self._text_cache))
            del self._text_cache[oldest]

        self._text_cache[text] = result
        return result

    def count_messages_tokens(self, messages: List[Dict[str, Any]]) -> int:
        """计算消息列表的 token 数量（带缓存）"""
        # 对于消息列表，使用哈希值作为缓存键
        import json
        cache_key = json.dumps(messages, sort_keys=True, ensure_ascii=False)

        if cache_key in self._text_cache:
            self._hit_count += 1
            return self._text_cache[cache_key]

        self._miss_count += 1
        result = self.base_counter.count_messages_tokens(messages)

        if len(self._text_cache) >= self._cache_size:
            oldest = next(iter(self._text_cache))
            del self._text_cache[oldest]

        self._text_cache[cache_key] = result
        return result

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        total = self._hit_count + self._miss_count
        hit_rate = self._hit_count / total if total > 0 else 0

        return {
            "cache_size": len(self._text_cache),
            "max_cache_size": self._cache_size,
            "hit_count": self._hit_count,
            "miss_count": self._miss_count,
            "hit_rate": hit_rate,
        }

    def clear_cache(self) -> None:
        """清空缓存"""
        self._text_cache.clear()
        self._hit_count = 0
        self._miss_count = 0
        logger.debug("Token 计数器缓存已清空")


class TokenCounterFactory:
    """Token 计数器工厂

    根据配置创建合适的计数器
    """

    @staticmethod
    def create(
        backend: TokenCounterBackend = TokenCounterBackend.ESTIMATE,
        enable_cache: bool = True,
        cache_size: int = 1000,
        encoding_name: str = "cl100k_base",
    ) -> BaseTokenCounter:
        """创建 Token 计数器

        Args:
            backend: 计数器后端类型
            enable_cache: 是否启用缓存
            cache_size: 缓存大小
            encoding_name: tiktoken 编码器名称

        Returns:
            Token 计数器实例
        """
        # 创建底层计数器
        if backend == TokenCounterBackend.ESTIMATE:
            counter = EstimateTokenCounter()
        elif backend in (TokenCounterBackend.TIKTOKEN,
                        TokenCounterBackend.CL100K_BASE,
                        TokenCounterBackend.O200K_BASE):
            encoding = encoding_name if backend == TokenCounterBackend.TIKTOKEN else backend.value
            counter = TikTokenCounter(encoding_name=encoding)
        else:
            logger.warning(f"未知的计数器后端: {backend}，使用估算模式")
            counter = EstimateTokenCounter()

        # 包装缓存层
        if enable_cache:
            counter = CachedTokenCounter(counter, cache_size=cache_size)

        logger.info(f"创建 Token 计数器: {backend.value}, 缓存: {enable_cache}")
        return counter


__all__ = [
    "TokenCounterBackend",
    "BaseTokenCounter",
    "EstimateTokenCounter",
    "TikTokenCounter",
    "CachedTokenCounter",
    "TokenCounterFactory",
]
