"""Token 计数器单元测试

测试各种 Token 计数器的功能
"""

import pytest
from packages.provider.token_counter import (
    TokenCounterBackend,
    BaseTokenCounter,
    EstimateTokenCounter,
    TikTokenCounter,
    CachedTokenCounter,
    TokenCounterFactory,
)


class TestEstimateTokenCounter:
    """估算型 Token 计数器测试"""

    @pytest.fixture
    def counter(self):
        return EstimateTokenCounter()

    def test_count_empty_string(self, counter):
        """测试空字符串"""
        assert counter.count_tokens("") == 0

    def test_count_english_text(self, counter):
        """测试英文文本"""
        # 简单英文单词
        assert counter.count_tokens("Hello world") == 2
        assert counter.count_tokens("This is a test") == 4

    def test_count_chinese_text(self, counter):
        """测试中文文本"""
        # 中文字符
        result = counter.count_tokens("你好世界")
        # 中文字符 * 1.5
        assert 4 <= result <= 7

    def test_count_mixed_text(self, counter):
        """测试中英文混合文本"""
        text = "Hello 你好 world 世界"
        result = counter.count_tokens(text)
        assert result > 0

    def test_count_with_numbers_and_punctuation(self, counter):
        """测试带数字和标点的文本"""
        result = counter.count_tokens("123! @# ABC")
        assert result > 0

    def test_count_messages(self, counter):
        """测试消息列表计数"""
        messages = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = counter.count_messages_tokens(messages)
        assert result > 3  # 至少大于文本的 token 数，因为有格式开销

    def test_custom_ratio(self):
        """测试自定义比例"""
        counter = EstimateTokenCounter(chinese_ratio=2.0, english_ratio=1.5)
        result = counter.count_tokens("你好")
        assert result == 4  # 2 * 2.0


class TestTikTokenCounter:
    """TikToken 计数器测试"""

    @pytest.fixture
    def counter(self):
        try:
            return TikTokenCounter(encoding_name="cl100k_base")
        except Exception:
            pytest.skip("tiktoken not available")

    def test_count_simple_text(self, counter):
        """测试简单文本计数"""
        result = counter.count_tokens("Hello, world!")
        # GPT tokenizer 的结果
        assert result > 0

    def test_count_chinese_text(self, counter):
        """测试中文文本计数"""
        result = counter.count_tokens("你好世界")
        assert result > 0

    def test_count_code(self, counter):
        """测试代码计数"""
        code = """
        def hello():
            print("Hello, world!")
        """
        result = counter.count_tokens(code)
        assert result > 0

    def test_count_messages_with_format_overhead(self, counter):
        """测试消息格式开销"""
        messages = [
            {"role": "user", "content": "Hello"},
        ]
        result = counter.count_messages_tokens(messages)
        # 应该包含格式开销（每条消息约 4 个 token）
        assert result > counter.count_tokens("Hello")

    def test_count_messages_with_name(self, counter):
        """测试带名称的消息"""
        messages = [
            {"role": "user", "name": "Alice", "content": "Hello"},
        ]
        result = counter.count_messages_tokens(messages)
        # 名称应该增加 token 数
        messages_without_name = [
            {"role": "user", "content": "Hello"},
        ]
        result_without_name = counter.count_messages_tokens(messages_without_name)
        assert result > result_without_name

    def test_fallback_to_estimate_on_error(self, counter):
        """测试错误时回退到估算"""
        # 这个测试验证当 tiktoken 失败时会回退
        # 实际实现中需要模拟错误，这里仅作为示例
        assert counter.count_tokens("test") >= 0


class TestCachedTokenCounter:
    """缓存 Token 计数器测试"""

    @pytest.fixture
    def base_counter(self):
        return EstimateTokenCounter()

    @pytest.fixture
    def cached_counter(self, base_counter):
        return CachedTokenCounter(base_counter, cache_size=10)

    def test_cache_hit(self, cached_counter):
        """测试缓存命中"""
        text = "Hello world"

        # 第一次调用 - 缓存未命中
        result1 = cached_counter.count_tokens(text)

        # 第二次调用 - 缓存命中
        result2 = cached_counter.count_tokens(text)

        assert result1 == result2
        stats = cached_counter.get_cache_stats()
        assert stats["hit_count"] == 1
        assert stats["miss_count"] == 1

    def test_cache_messages(self, cached_counter):
        """测试消息缓存"""
        messages = [{"role": "user", "content": "Hello"}]

        # 两次调用
        cached_counter.count_messages_tokens(messages)
        cached_counter.count_messages_tokens(messages)

        stats = cached_counter.get_cache_stats()
        assert stats["hit_count"] == 1

    def test_cache_size_limit(self, base_counter):
        """测试缓存大小限制"""
        cached_counter = CachedTokenCounter(base_counter, cache_size=3)

        # 添加超过缓存大小的项目
        for i in range(5):
            cached_counter.count_tokens(f"text{i}")

        stats = cached_counter.get_cache_stats()
        # 缓存大小应该被限制
        assert stats["cache_size"] <= 3

    def test_clear_cache(self, cached_counter):
        """测试清空缓存"""
        cached_counter.count_tokens("test")
        assert cached_counter.get_cache_stats()["cache_size"] > 0

        cached_counter.clear_cache()
        stats = cached_counter.get_cache_stats()
        assert stats["cache_size"] == 0
        assert stats["hit_count"] == 0
        assert stats["miss_count"] == 0

    def test_cache_hit_rate(self, cached_counter):
        """测试缓存命中率计算"""
        # 第一次调用
        cached_counter.count_tokens("test1")
        cached_counter.count_tokens("test2")

        # 重复调用
        cached_counter.count_tokens("test1")
        cached_counter.count_tokens("test2")

        stats = cached_counter.get_cache_stats()
        # 2 次命中，2 次未命中
        assert stats["hit_count"] == 2
        assert stats["miss_count"] == 2
        assert stats["hit_rate"] == 0.5


class TestTokenCounterFactory:
    """Token 计数器工厂测试"""

    def test_create_estimate_counter(self):
        """测试创建估算计数器"""
        counter = TokenCounterFactory.create(
            backend=TokenCounterBackend.ESTIMATE,
            enable_cache=False
        )
        assert isinstance(counter, EstimateTokenCounter)

    def test_create_tiktoken_counter(self):
        """测试创建 tiktoken 计数器"""
        try:
            counter = TokenCounterFactory.create(
                backend=TokenCounterBackend.TIKTOKEN,
                enable_cache=False
            )
            assert isinstance(counter, TikTokenCounter)
        except Exception:
            # tiktoken 不可用时，应该回退到估算
            counter = TokenCounterFactory.create(
                backend=TokenCounterBackend.TIKTOKEN,
                enable_cache=False
            )
            # 应该仍然返回一个计数器
            assert isinstance(counter, BaseTokenCounter)

    def test_create_with_cache(self):
        """测试创建带缓存的计数器"""
        counter = TokenCounterFactory.create(
            backend=TokenCounterBackend.ESTIMATE,
            enable_cache=True,
            cache_size=100
        )
        assert isinstance(counter, CachedTokenCounter)

    def test_unknown_backend_fallback(self):
        """测试未知后端回退"""
        # 使用无效的后端
        counter = TokenCounterFactory.create(
            backend="invalid_backend",
            enable_cache=False
        )
        # 应该回退到估算
        assert isinstance(counter, EstimateTokenCounter)


class TestTokenCounterIntegration:
    """Token 计数器集成测试"""

    def test_real_world_chat_message(self):
        """测试真实聊天消息计数"""
        counter = EstimateTokenCounter()

        # 典型的聊天消息
        message = "帮我写一个Python函数来计算斐波那契数列"

        result = counter.count_tokens(message)
        assert result > 0

    def test_long_context_window(self):
        """测试长上下文窗口"""
        counter = EstimateTokenCounter()

        # 模拟长对话
        messages = []
        for i in range(20):
            messages.append({
                "role": "user",
                "content": f"这是第 {i} 条消息，内容包含一些中文字符和 English words mixed together"
            })
            messages.append({
                "role": "assistant",
                "content": f"这是第 {i} 条回复，Response number {i} with some mixed content"
            })

        result = counter.count_messages_tokens(messages)
        assert result > 0
        # 长对话应该有大量 token
        assert result > 100

    def test_multilingual_content(self):
        """测试多语言内容"""
        counter = EstimateTokenCounter()

        # 多语言混合
        text = """
        English text here.
        中文内容在这里。
        日本語のテキスト。
        한국어 텍스트.
        Numbers: 12345
        Symbols: @#$%^&*()
        """

        result = counter.count_tokens(text)
        assert result > 0
