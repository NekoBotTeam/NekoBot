# NekoBot 增强功能文档

本文档介绍了 NekoBot 新增的增强功能模块及其使用方法。

## 概述

新增的增强功能模块提供了以下核心能力：

- **运行时管理**: 动态添加/移除平台实例、配置热更新、生命周期管理
- **连接管理**: 自动重连、健康检查、心跳检测
- **故障隔离**: 异常捕获、自动恢复、降级模式
- **消息路由**: 统一入口、优先级队列、去重机制
- **消息缓冲**: 离线暂存、消息回放、缓冲策略
- **状态监控**: 实时状态展示、吞吐量统计、错误率监控
- **配置版本控制**: 变更历史、配置回滚、差异展示

## 模块详细说明

### 1. 运行时管理 (`runtime_manager.py`)

提供平台实例的动态管理能力。

**主要功能:**
- 动态添加/移除单个平台实例（无需重启整个系统）
- 配置热更新能力（修改配置后立即生效）
- 平台实例的生命周期管理（启动、停止、重启）

**使用示例:**

```python
from packages.core import runtime_manager

# 添加平台
await runtime_manager.add_platform(
    platform_id="new_platform",
    platform_config={"type": "qq", "enable": True},
    auto_start=True
)

# 启动平台
await runtime_manager.start_platform("new_platform")

# 停止平台
await runtime_manager.stop_platform("new_platform")

# 重启平台
await runtime_manager.restart_platform("new_platform")

# 更新平台配置
await runtime_manager.update_platform_config(
    platform_id="new_platform",
    config_updates={"enable": True, "name": "Updated Name"},
    apply_immediately=True
)

# 移除平台
await runtime_manager.remove_platform("new_platform")

# 获取生命周期状态
status = runtime_manager.get_platform_lifecycle_status("new_platform")
```

**API 接口:**
- `GET /api/runtime/lifecycle` - 获取生命周期状态
- `POST /api/runtime/lifecycle` - 管理生命周期（启动/停止/重启）
- `POST /api/runtime/platforms` - 添加平台
- `DELETE /api/runtime/platforms` - 移除平台

### 2. 连接管理 (`connection_manager.py`)

提供平台连接的自动重连、健康检查和心跳检测。

**主要功能:**
- 自动重连机制（连接断开后自动尝试重连）
- 连接健康检查和心跳检测
- 连接失败通知和告警

**使用示例:**

```python
from packages.core import ConnectionManager, ConnectionConfig

# 创建连接管理器
config = ConnectionConfig(
    auto_reconnect=True,
    max_reconnect_attempts=5,
    reconnect_interval=5.0,
    health_check_interval=60.0,
    heartbeat_interval=30.0,
)

conn_manager = ConnectionManager("platform_id", config)

# 设置连接回调
async def on_connect():
    print("连接成功")

async def on_disconnect():
    print("连接断开")

conn_manager.set_callbacks(
    connect_callback=on_connect,
    disconnect_callback=on_disconnect,
)

# 建立连接
await conn_manager.connect()

# 获取连接统计
stats = conn_manager.get_connection_stats()
```

**API 接口:**
- `GET /api/connection/stats` - 获取连接统计
- `POST /api/connection/config` - 更新连接配置

### 3. 故障隔离 (`fault_isolation.py`)

提供平台异常的隔离、捕获、自动恢复和降级运行模式。

**主要功能:**
- 单个平台异常不应影响其他平台
- 异常捕获和自动恢复策略
- 降级运行模式（部分平台故障时继续运行）

**使用示例:**

```python
from packages.core import fault_isolation_manager

# 处理故障
await fault_isolation_manager.handle_fault(
    platform_id="platform_id",
    exception=Exception("Some error"),
    context={"additional_info": "..."}
)

# 启用平台
await fault_isolation_manager.enable_platform("platform_id")

# 禁用平台
await fault_isolation_manager.disable_platform("platform_id")

# 获取故障记录
records = fault_isolation_manager.get_fault_records("platform_id")

# 获取隔离状态
status = fault_isolation_manager.get_isolation_status()
```

**API 接口:**
- `GET /api/fault/isolation` - 获取隔离状态
- `GET /api/fault/records` - 获取故障记录
- `POST /api/fault/platform/enable` - 启用平台
- `POST /api/fault/platform/disable` - 禁用平台

### 4. 消息路由 (`message_router.py`)

提供平台消息到消息处理系统的统一入口。

**主要功能:**
- 平台消息到消息处理系统的统一入口
- 消息优先级队列（重要消息优先处理）
- 消息去重和幂等性保证

**使用示例:**

```python
from packages.core import MessageRouter, MessagePriority

# 创建消息路由器（已在 server.py 中全局初始化）
# message_router = MessageRouter(max_queue_size=1000, enable_dedup=True)

# 启动路由器
await message_router.start()

# 路由消息
await message_router.route_message(
    platform_id="platform_id",
    message_type="message",
    content={"message_id": "123", "text": "Hello"},
    priority=MessagePriority.HIGH
)

# 注册消息处理器
async def handle_message(message):
    print(f"处理消息: {message.content}")
    return True

message_router.register_handler("message", handle_message)

# 获取统计
stats = message_router.get_stats()
```

**API 接口:**
- `GET /api/message/router/stats` - 获取路由统计

### 5. 消息缓冲 (`message_buffer.py`)

提供平台离线时的消息暂存机制。

**主要功能:**
- 平台离线时的消息暂存机制
- 平台恢复后的消息回放
- 缓冲区大小和过期策略

**使用示例:**

```python
from packages.core import MessageBuffer, BufferPolicy

# 创建消息缓冲器（已在 server.py 中全局初始化）
# message_buffer = MessageBuffer(max_size=1000, buffer_policy=BufferPolicy.FIFO)

# 标记平台离线
message_buffer.mark_platform_offline("platform_id")

# 添加消息到缓冲
await message_buffer.add_message(
    platform_id="platform_id",
    message_type="message",
    content={"message_id": "123", "text": "Hello"},
    priority=1,
    ttl=3600  # 1小时过期
)

# 标记平台在线
message_buffer.mark_platform_online("platform_id")

# 回放消息
replayed = await message_buffer.replay_messages("platform_id", max_count=100)

# 获取缓冲统计
stats = message_buffer.get_buffer_stats()
```

**API 接口:**
- `GET /api/message/buffer/stats` - 获取缓冲统计
- `GET /api/message/buffer/messages` - 获取缓冲消息
- `POST /api/message/buffer/replay` - 回放消息

### 6. 状态监控 (`status_monitor.py`)

提供平台运行状态的实时展示。

**主要功能:**
- 平台运行状态实时展示
- 消息吞吐量和延迟统计
- 错误率监控

**使用示例:**

```python
from packages.core import StatusMonitor, MetricType, AlertLevel

# 创建状态监控器（已在 server.py 中全局初始化）
# status_monitor = StatusMonitor(history_size=1000)

# 启动监控器
await status_monitor.start()

# 记录指标
status_monitor.record_metric(
    name="memory_usage",
    value=1024 * 1024 * 100,
    metric_type=MetricType.GAUGE
)

# 记录消息
status_monitor.record_message(
    platform_id="platform_id",
    message_type="message",
    latency_ms=150,
    success=True
)

# 注册告警规则
async def high_latency_rule(monitor: StatusMonitor):
    platform_status = monitor.get_platform_status("platform_id")
    if platform_status["avg_latency_ms"] > 5000:
        from packages.core import Alert, AlertLevel
        return Alert(
            alert_id="high_latency",
            level=AlertLevel.WARNING,
            message=f"平台延迟过高: {platform_status['avg_latency_ms']}ms",
            platform_id="platform_id",
            metric_name="latency"
        )
    return None

status_monitor.register_alert_rule(high_latency_rule)

# 获取平台状态
platform_status = status_monitor.get_platform_status("platform_id")

# 获取告警
alerts = status_monitor.get_alerts(level=AlertLevel.WARNING)
```

**API 接口:**
- `GET /api/monitor/status` - 获取监控状态
- `GET /api/monitor/platforms` - 获取平台监控状态
- `GET /api/monitor/alerts` - 获取告警列表
- `POST /api/monitor/alerts/resolve` - 解决告警

### 7. 配置版本控制 (`config_version_manager.py`)

提供配置变更历史记录和回滚能力。

**主要功能:**
- 配置变更历史记录
- 配置回滚能力
- 配置比较和差异展示

**使用示例:**

```python
from packages.config import ConfigVersionManager, ConfigChangeType

# 创建配置版本管理器
config_manager = ConfigVersionManager(max_versions=50)

# 创建版本
version = config_manager.create_version(
    config={"key": "value"},
    change_type=ConfigChangeType.UPDATE,
    description="更新配置",
    author="admin"
)

# 列出版本
versions = config_manager.list_versions(limit=10)

# 回滚到指定版本
new_version = config_manager.rollback_to_version(
    version_id="v20250122120000",
    description="回滚到之前的版本"
)

# 比较版本
diff = config_manager.compare_versions(
    version_id1="v20250122120000",
    version_id2="v20250122130000"
)

# 导出版本
config_manager.export_version(
    version_id="v20250122120000",
    file_path="config_backup.json"
)

# 导入版本
config_manager.import_version(
    file_path="config_backup.json",
    description="从备份导入"
)
```

## 集成到现有代码

所有增强功能管理器已在 `packages/core/server.py` 中初始化，可以作为全局变量使用：

```python
from packages.core.server import (
    runtime_manager,
    message_router,
    message_buffer,
    status_monitor,
    fault_isolation_manager,
)
```

## 最佳实践

1. **使用运行时管理器**：在需要动态管理平台时，优先使用运行时管理器而不是直接操作平台管理器。

2. **连接管理**：为每个平台实例创建连接管理器，以获得自动重连和健康检查功能。

3. **故障隔离**：在平台适配器的异常处理中，将异常传递给故障隔离管理器。

4. **消息路由**：将平台消息通过消息路由器分发，以获得优先级队列和去重功能。

5. **消息缓冲**：在平台离线时，自动使用消息缓冲器暂存消息。

6. **状态监控**：定期记录指标和消息，以获得完整的监控数据。

7. **配置版本控制**：在每次配置变更时创建版本，以便需要时可以回滚。

## 注意事项

- 所有管理器都需要在服务器启动后才能使用
- 消息路由器和状态监控器需要显式调用 `start()` 方法启动
- 连接管理器需要平台适配器提供具体的实现
- 配置版本控制需要足够的磁盘空间来存储版本历史
- 建议定期清理过期的版本和监控数据

## 性能考虑

- 消息路由器的队列大小应根据实际消息量调整
- 监控指标的历史大小会影响内存使用
- 消息缓冲器的持久化功能会增加磁盘 I/O
- 故障隔离的恢复检查间隔应根据实际情况调整
