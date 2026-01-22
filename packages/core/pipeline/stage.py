"""Pipeline Stage 基类

定义 Pipeline 的某个阶段，支持洋葱模型

洋葱模型 (Onion Model):
=====================
洋葱模型是一种中间件模式，允许在阶段执行前后插入处理逻辑。

执行流程:
    Stage1.pre -> Stage2.pre -> Stage3.pre -> Stage3.post -> Stage2.post -> Stage1.post

实现方式:
    使用 AsyncGenerator 实现，通过 yield 分割前置和后置处理:

    async def process(self, event: dict, ctx: PipelineContext) -> AsyncGenerator[None, None]:
        # === 前置处理 ===
        await self._do_something_before(event, ctx)

        # yield 暂停点：交出控制权给下一个阶段
        yield

        # === 后置处理 ===
        await self._do_something_after(event, ctx)

简化模式（非洋葱）:
    如果不需要洋葱模型，可以返回 None 或普通协程:

    async def process(self, event: dict, ctx: PipelineContext) -> None:
        # 处理逻辑
        pass

使用场景:
    - 前置处理：数据验证、权限检查、日志记录、性能监控开始
    - 后置处理：资源清理、统计上报、性能监控结束、错误处理
"""

import abc
from typing import AsyncGenerator, Optional, Type, Dict
from loguru import logger
from .context import PipelineContext


# 全局 Stage 注册表
_stage_registry: Dict[str, Type["Stage"]] = {}
"""维护已注册的 Stage 类，按类名索引"""


class Stage(abc.ABC):
    """描述一个 Pipeline 的某个阶段

    支持洋葱模型和简化模式两种实现方式。

    洋葱模型示例:
        @register_stage
        class MyStage(Stage):
            async def initialize(self, ctx: PipelineContext) -> None:
                pass

            async def process(self, event: dict, ctx: PipelineContext) -> AsyncGenerator[None, None]:
                # 前置处理
                event["start_time"] = time.time()

                # 暂停并交给下一个阶段
                yield

                # 后置处理
                duration = time.time() - event["start_time"]
                logger.info(f"处理耗时: {duration}s")

    简化模式示例:
        @register_stage
        class SimpleStage(Stage):
            async def initialize(self, ctx: PipelineContext) -> None:
                pass

            async def process(self, event: dict, ctx: PipelineContext) -> None:
                # 简单处理，不需要后置逻辑
                logger.info("处理事件")
    """

    @abc.abstractmethod
    async def initialize(self, ctx: PipelineContext) -> None:
        """初始化阶段

        Args:
            ctx: Pipeline 上下文

        Note:
            此方法在 Pipeline 首次执行时调用，用于初始化阶段状态
        """
        pass

    @abc.abstractmethod
    async def process(
        self, event: dict, ctx: PipelineContext
    ) -> Optional[AsyncGenerator[None, None]]:
        """处理事件，返回 None 或异步生成器

        Args:
            event: 事件数据
            ctx: Pipeline 上下文

        Returns:
            - None: 简化模式，直接进入下一个阶段
            - AsyncGenerator: 洋葱模型，支持前置和后置处理

        Note:
            返回 AsyncGenerator 时，yield 之前是前置处理，yield 之后是后置处理
        """
        pass


def register_stage(stage_cls: type) -> type:
    """注册 Stage 的装饰器

    Args:
        stage_cls: Stage 类

    Returns:
        Stage 类
    """
    stage_name = stage_cls.__name__

    if stage_name in _stage_registry:
        logger.warning(
            f"Stage {stage_name} 已存在，将被覆盖。"
        )

    _stage_registry[stage_name] = stage_cls

    return stage_cls


def get_stage(stage_name: str) -> Optional[Type["Stage"]]:
    """获取已注册的 Stage 类

    Args:
        stage_name: Stage 类名

    Returns:
        Stage 类，如果未找到则返回 None
    """
    return _stage_registry.get(stage_name)


def list_stages() -> Dict[str, Type["Stage"]]:
    """列出所有已注册的 Stage

    Returns:
        Stage 名称到类的映射
    """
    return _stage_registry.copy()


def unregister_stage(stage_name: str) -> bool:
    """注销 Stage

    Args:
        stage_name: Stage 类名

    Returns:
        是否成功注销
    """
    if stage_name in _stage_registry:
        del _stage_registry[stage_name]
        return True
    return False
