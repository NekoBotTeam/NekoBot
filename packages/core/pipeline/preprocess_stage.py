"""预处理阶段

在主处理流程之前执行预处理操作，支持洋葱模型

洋葱模型用法:
    async def process(self, event: dict, ctx: PipelineContext) -> AsyncGenerator[None, None]:
        # 前置处理（在 yield 之前执行）
        await self._do_preprocessing(event, ctx)

        # yield 暂停点：将控制权交给下一个阶段
        yield

        # 后置处理（在后续阶段完成后执行）
        await self._do_postprocessing(event, ctx)
"""

from typing import AsyncGenerator, Optional
from loguru import logger

from .stage import Stage, register_stage
from .context import PipelineContext


@register_stage
class PreProcessStage(Stage):
    """预处理阶段

    此阶段在主处理流程之前执行，提供:
    1. 事件数据清洗和标准化
    2. 事件元数据注入
    3. 早期过滤和验证
    4. 性能监控埋点

    使用洋葱模型支持后置处理（如资源清理、统计上报）
    """

    async def initialize(self, ctx: PipelineContext) -> None:
        """初始化阶段"""
        self.ctx = ctx

        # 性能监控配置
        self.enable_performance_tracking = ctx.config.get(
            "performance_tracking", {}
        ).get("enabled", False)

        # 事件清洗配置
        self.enable_event_sanitization = ctx.config.get(
            "event_sanitization", {}
        ).get("enabled", True)

        # 元数据注入配置
        self.enable_metadata_injection = ctx.config.get(
            "metadata_injection", {}
        ).get("enabled", True)

        logger.debug(
            f"PreProcessStage 初始化: "
            f"performance_tracking={self.enable_performance_tracking}, "
            f"event_sanitization={self.enable_event_sanitization}, "
            f"metadata_injection={self.enable_metadata_injection}"
        )

    async def process(
        self, event: dict, ctx: PipelineContext
    ) -> Optional[AsyncGenerator[None, None]]:
        """预处理事件（洋葱模型）

        Args:
            event: 事件数据
            ctx: Pipeline 上下文

        Returns:
            异步生成器（洋葱模型）
        """
        # ===== 前置处理 =====

        # 1. 注入时间戳（如果不存在）
        if self.enable_metadata_injection:
            self._inject_timestamp(event)

        # 2. 注入会话标识符
        if self.enable_metadata_injection:
            self._inject_session_id(event, ctx)

        # 3. 事件数据清洗
        if self.enable_event_sanitization:
            self._sanitize_event_data(event)

        # 4. 性能监控埋点
        if self.enable_performance_tracking:
            self._start_performance_tracking(event)

        # 5. 早期验证和过滤
        should_stop = await self._early_validation(event, ctx)
        if should_stop:
            # 验证失败，停止事件传播
            return

        logger.debug(f"预处理完成: post_type={event.get('post_type')}")

        # ===== yield 暂停点：将控制权交给下一个阶段 =====
        yield

        # ===== 后置处理（后续阶段完成后执行）=====

        # 1. 性能监控结束和记录
        if self.enable_performance_tracking:
            self._end_performance_tracking(event)

        # 2. 事件统计上报
        await self._report_event_statistics(event, ctx)

        # 3. 资源清理
        await self._cleanup_resources(event, ctx)

        logger.debug(f"后置处理完成: post_type={event.get('post_type')}")

    # ===== 前置处理方法 =====

    def _inject_timestamp(self, event: dict) -> None:
        """注入时间戳"""
        if "_timestamp" not in event:
            import time
            event["_timestamp"] = time.time()

    def _inject_session_id(self, event: dict, ctx: PipelineContext) -> None:
        """注入会话标识符

        生成统一的会话 ID，格式: platform:message_type:user_id
        或 platform:message_type:group_id:user_id（群聊）
        """
        if "_session_id" not in event:
            platform_id = event.get("platform_id", "unknown")
            message_type = event.get("message_type", "unknown")
            user_id = str(event.get("user_id", "unknown"))
            group_id = str(event.get("group_id", ""))

            if message_type == "group" and group_id:
                event["_session_id"] = f"{platform_id}:group:{group_id}:{user_id}"
            else:
                event["_session_id"] = f"{platform_id}:private:{user_id}"

            # 同时注入到 context 中
            ctx.session_id = event["_session_id"]
            ctx.user_id = user_id
            if group_id:
                ctx.group_id = group_id

    def _sanitize_event_data(self, event: dict) -> None:
        """清洗事件数据

        1. 移除空字段
        2. 标准化消息格式
        3. 过滤敏感信息（根据配置）
        """
        # 移除 None 值的字段
        keys_to_remove = [k for k, v in event.items() if v is None]
        for key in keys_to_remove:
            del event[key]

        # 标准化消息格式
        message = event.get("message")
        if isinstance(message, list):
            # 确保每个消息段都有 type 和 data 字段
            for seg in message:
                if isinstance(seg, dict):
                    if "type" not in seg:
                        seg["type"] = "unknown"
                    if "data" not in seg:
                        seg["data"] = {}

    async def _early_validation(self, event: dict, ctx: PipelineContext) -> bool:
        """早期验证和过滤

        Returns:
            True 表示应该停止事件传播
        """
        post_type = event.get("post_type")

        # 验证必要字段
        if post_type == "message":
            # 消息事件必须有 message 字段
            if "message" not in event:
                logger.warning("消息事件缺少 message 字段，忽略")
                return True

        elif post_type == "notice":
            # 通知事件必须有 notice_type 字段
            if "notice_type" not in event:
                logger.warning("通知事件缺少 notice_type 字段，忽略")
                return True

        elif post_type == "request":
            # 请求事件必须有 request_type 字段
            if "request_type" not in event:
                logger.warning("请求事件缺少 request_type 字段，忽略")
                return True

        return False

    def _start_performance_tracking(self, event: dict) -> None:
        """开始性能监控"""
        import time
        event["_perf_start"] = time.time()

    # ===== 后置处理方法 =====

    def _end_performance_tracking(self, event: dict) -> None:
        """结束性能监控"""
        if "_perf_start" in event:
            import time
            duration = time.time() - event["_perf_start"]
            event["_perf_duration"] = duration

            # 记录慢事件
            if duration > 1.0:
                post_type = event.get("post_type", "unknown")
                logger.warning(f"慢事件检测: post_type={post_type}, duration={duration:.2f}s")

    async def _report_event_statistics(self, event: dict, ctx: PipelineContext) -> None:
        """上报事件统计"""
        # 这里可以集成到统计系统
        # 例如：记录事件类型计数、平均处理时长等
        pass

    async def _cleanup_resources(self, event: dict, ctx: PipelineContext) -> None:
        """清理临时资源"""
        # 清理临时字段
        temp_fields = ["_perf_start"]
        for field in temp_fields:
            event.pop(field, None)
