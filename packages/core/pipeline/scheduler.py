"""Pipeline 调度器

支持洋葱模型的流水线调度器，提供前置/后置处理能力
参考 AstrBot 的 PipelineScheduler 实现，优化性能和可维护性
"""

import time
from typing import List, Optional, AsyncGenerator, Dict, Any
from loguru import logger
import traceback

from .stage import Stage
from .context import PipelineContext
from .event_stopper import EventStopper


class PipelineScheduler:
    """管道调度器，支持洋葱模型的事件处理（优化版）

    洋葱模型特点：
    - 支持 AsyncGenerator 实现 yield 暂停点
    - yield 之前是前置处理
    - yield 之后是后置处理
    - 支持事件传播控制

    性能优化：
    - 阶段执行时间统计
    - 异常隔离处理
    - 简化的事件停止检查
    """

    def __init__(self, stages: List[Stage], context: Optional[PipelineContext] = None):
        """初始化调度器

        Args:
            stages: 阶段列表（已按顺序排序）
            context: Pipeline 上下文
        """
        self.stages = stages
        self.context = context
        self._initialized = False

        # 性能统计
        self._stage_stats: Dict[str, float] = {}
        self._total_executions = 0
        self._total_errors = 0

    async def execute(self, event: dict, ctx: Optional[PipelineContext] = None) -> None:
        """执行所有阶段（洋葱模型）

        Args:
            event: 事件数据
            ctx: Pipeline 上下文（如果提供，覆盖构造时的 context）
        """
        # 使用提供的 context 或构造时的 context
        pipeline_ctx = ctx or self.context

        # 首次执行时初始化所有阶段
        if not self._initialized:
            logger.info("开始初始化Pipeline阶段...")
            for stage in self.stages:
                try:
                    await stage.initialize(pipeline_ctx)
                except Exception as e:
                    logger.error(f"阶段 {stage.__class__.__name__} 初始化失败: {e}")
            logger.info(f"Pipeline阶段初始化完成，共 {len(self.stages)} 个阶段")
            self._initialized = True

        # 确保事件中有 EventStopper
        self._ensure_event_stopper(event)

        # 统计执行次数
        self._total_executions += 1
        start_time = time.time()

        try:
            # 开始执行流水线（从第 0 个阶段开始）
            await self._process_stages(event, pipeline_ctx, from_stage=0)
        except Exception as e:
            self._total_errors += 1
            logger.error(f"流水线执行失败: {e}")
            logger.error(traceback.format_exc())
        finally:
            # 记录执行时间
            elapsed = time.time() - start_time
            if elapsed > 1.0:  # 超过1秒记录警告
                logger.warning(f"Pipeline 执行耗时 {elapsed:.2f}s")

    async def _process_stages(
        self, event: dict, ctx: PipelineContext, from_stage: int = 0
    ) -> None:
        """依次执行各个阶段 - 洋葱模型实现（优化版）

        Args:
            event: 事件数据
            ctx: Pipeline 上下文
            from_stage: 起始阶段索引
        """
        event_stopper = event.get("_stopper")

        for i in range(from_stage, len(self.stages)):
            # 简化的停止检查（借鉴 AstrBot）
            if self._is_event_stopped(event):
                logger.debug(f"事件已停止，终止流水线执行（阶段 {i}）")
                return

            stage = self.stages[i]
            stage_name = stage.__class__.__name__
            start_time = time.time()

            try:
                # 调用阶段的 process 方法
                result = await stage.process(event, ctx)

                # 记录阶段耗时
                elapsed = time.time() - start_time
                self._update_stage_stats(stage_name, elapsed)

                if result is None:
                    # 阶段返回 None，继续下一个阶段
                    continue

                # 检查是否是异步生成器（洋葱模型）
                if isinstance(result, AsyncGenerator):
                    async for _ in result:
                        # 暂停点：前置处理已完成

                        # 检查事件是否已停止
                        if self._is_event_stopped(event):
                            logger.debug(f"事件已停止（前置处理后，阶段 {stage_name}）")
                            return

                        # 递归处理后续阶段
                        await self._process_stages(event, ctx, i + 1)

                        # 暂停点返回：后续阶段已完成，执行后置处理

                        # 检查事件是否已停止
                        if self._is_event_stopped(event):
                            logger.debug(f"事件已停止（后置处理后，阶段 {stage_name}）")
                            return
                else:
                    # 普通协程，等待完成
                    await result

            except Exception as e:
                self._total_errors += 1
                logger.error(f"阶段 {stage_name} 执行失败: {e}")
                logger.debug(traceback.format_exc())
                # 继续执行下一个阶段（异常隔离）

    def _ensure_event_stopper(self, event: dict) -> None:
        """确保事件中有 EventStopper

        Args:
            event: 事件数据
        """
        if event.get("_stopper") is None:
            event["_stopper"] = EventStopper()

    def _is_event_stopped(self, event: dict) -> bool:
        """检查事件是否已停止（简化版）

        Args:
            event: 事件数据

        Returns:
            是否已停止
        """
        event_stopper = event.get("_stopper")
        return event_stopper is not None and event_stopper.is_stopped()

    def _update_stage_stats(self, stage_name: str, elapsed: float) -> None:
        """更新阶段统计信息

        Args:
            stage_name: 阶段名称
            elapsed: 执行时间（秒）
        """
        if stage_name not in self._stage_stats:
            self._stage_stats[stage_name] = 0.0
        self._stage_stats[stage_name] += elapsed

        # 警告慢阶段
        if elapsed > 0.5:  # 超过500ms
            logger.warning(f"阶段 {stage_name} 执行较慢: {elapsed:.3f}s")

    def stop_event(self, event: dict, reason: str = "") -> None:
        """停止事件传播

        Args:
            event: 事件数据
            reason: 停止原因
        """
        event_stopper = event.get("_stopper")
        if event_stopper:
            event_stopper.stop(reason)
            logger.debug(f"事件传播已停止: {reason}")

    def reset_event(self, event: dict) -> None:
        """重置事件停止状态

        Args:
            event: 事件数据
        """
        event_stopper = event.get("_stopper")
        if event_stopper:
            event_stopper.reset()
            logger.debug("事件停止状态已重置")

    def is_event_stopped(self, event: dict) -> bool:
        """检查事件是否已停止

        Args:
            event: 事件数据

        Returns:
            是否已停止
        """
        event_stopper = event.get("_stopper")
        if event_stopper:
            return event_stopper.is_stopped()
        return False

    async def initialize_stages(self, ctx: PipelineContext) -> None:
        """初始化所有阶段

        Args:
            ctx: Pipeline 上下文
        """
        logger.info("开始初始化Pipeline阶段...")
        for stage in self.stages:
            try:
                await stage.initialize(ctx)
            except Exception as e:
                logger.error(f"阶段 {stage.__class__.__name__} 初始化失败: {e}")
        logger.info(f"Pipeline阶段初始化完成，共 {len(self.stages)} 个阶段")
        self._initialized = True

    def get_stages(self) -> List[Stage]:
        """获取所有阶段

        Returns:
            阶段列表
        """
        return self.stages.copy()

    def get_stage_names(self) -> List[str]:
        """获取所有阶段名称

        Returns:
            阶段名称列表
        """
        return [stage.__class__.__name__ for stage in self.stages]

    # ========== 性能统计方法 ==========

    def get_stats(self) -> Dict[str, Any]:
        """获取 Pipeline 性能统计信息

        Returns:
            统计信息字典
        """
        return {
            "total_executions": self._total_executions,
            "total_errors": self._total_errors,
            "error_rate": (
                self._total_errors / self._total_executions
                if self._total_executions > 0
                else 0
            ),
            "stage_stats": {
                stage: {
                    "total_time": round(time_val, 3),
                    "avg_time": round(time_val / max(1, self._total_executions), 3)
                }
                for stage, time_val in self._stage_stats.items()
            },
            "total_stage_time": round(sum(self._stage_stats.values()), 3),
            "num_stages": len(self.stages),
        }

    def reset_stats(self) -> None:
        """重置性能统计信息"""
        self._stage_stats.clear()
        self._total_executions = 0
        self._total_errors = 0
        logger.debug("Pipeline 统计信息已重置")

    def get_slowest_stages(self, limit: int = 5) -> List[tuple[str, float]]:
        """获取最慢的阶段列表

        Args:
            limit: 返回的最大数量

        Returns:
            (阶段名称, 总时间) 元组列表，按时间降序排列
        """
        return sorted(
            self._stage_stats.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]
