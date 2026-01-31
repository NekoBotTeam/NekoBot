# NekoBot 项目装饰器使用全景分析

## 概述

NekoBot 项目是一个**重度使用装饰器**的项目，采用**声明式编程**和**注册表模式**构建整个架构。装饰器在项目中扮演着核心角色，负责组件注册、错误处理、请求验证等功能。

---

## 一、装饰器类型总览

### 1. 标准库装饰器

| 装饰器 | 使用次数 | 用途 |
|--------|---------|------|
| `@dataclass` | 50+ | 数据类定义，替代 `__init__` |
| `@abstractmethod` | 20+ | 抽象方法定义 |
| `@staticmethod` | 15+ | 静态方法 |
| `@classmethod` | 10+ | 类方法 |
| `@property` | 8+ | 属性访问器 |

### 2. 框架装饰器（Quart/Flask）

| 装饰器 | 使用次数 | 用途 |
|--------|---------|------|
| `@app.get()` | 20+ | GET 路由注册 |
| `@app.post()` | 15+ | POST 路由注册 |
| `@app.websocket()` | 5+ | WebSocket 路由 |
| `@app.before_request` | 2+ | 请求前处理 |

### 3. 自定义注册装饰器（核心架构）

| 装饰器 | 使用次数 | 模块 | 用途 |
|--------|---------|------|------|
| `@register_platform_adapter()` | 8+ | platform/register.py | 平台适配器注册 |
| `@register_llm_provider()` | 10+ | provider/register.py | LLM Provider注册 |
| `@register_tts_provider()` | 5+ | provider/register.py | TTS Provider注册 |
| `@register_stt_provider()` | 3+ | provider/register.py | STT Provider注册 |
| `@register_embedding_provider()` | 2+ | provider/register.py | Embedding Provider注册 |
| `@register_rerank_provider()` | 2+ | provider/register.py | Rerank Provider注册 |
| `@register_stage()` | 12+ | core/pipeline/stage.py | Pipeline Stage注册 |
| `@register_tool()` | 5+ | agent/tools/registry.py | Agent工具注册 |
| `@register()` | 5+ | core/command_management.py | 命令注册 |
| `@BackupRegistry.register()` | 14+ | core/backup/config.py | **备份项注册（新增）** |

### 4. 通用装饰器

| 装饰器 | 使用次数 | 模块 | 用途 |
|--------|---------|------|------|
| `@handle_route_errors()` | 10+ | common/decorators.py | 路由错误处理 |
| `@handle_async_errors()` | 8+ | common/decorators.py | 异步错误处理 |
| `@validate_request_data()` | 10+ | common/decorators.py | 请求数据验证 |
| `@with_error_handling()` | 5+ | common/decorators.py | 通用错误处理 |
| `@cache_result()` | 2+ | common/decorators.py | 结果缓存 |

---

## 二、核心注册装饰器详解

### 2.1 Provider注册装饰器

**模块**: `packages/provider/register.py`

**装饰器列表**:
- `@register_llm_provider()` - LLM Provider
- `@register_tts_provider()` - TTS Provider
- `@register_stt_provider()` - STT Provider
- `@register_embedding_provider()` - Embedding Provider
- `@register_rerank_provider()` - Rerank Provider

**使用示例**:
```python
@register_llm_provider("openai", "OpenAI")
class OpenAIProvider(BaseLLMProvider):
    pass

@register_tts_provider("edge_tts", "Edge TTS")
class EdgeTTSProvider(BaseTTSProvider):
    pass
```

**注册表**:
- `llm_provider_registry: List[ProviderMetaData]`
- `tts_provider_registry: List[ProviderMetaData]`
- `provider_cls_map: Dict[str, ProviderMetaData]`

---

### 2.2 平台适配器注册装饰器

**模块**: `packages/platform/register.py`

**装饰器**: `@register_platform_adapter()`

**使用示例**:
```python
@register_platform_adapter(
    "qq",
    "OneBot V11",
    support_streaming_message=False
)
class QQAdapter(BasePlatformAdapter):
    pass

@register_platform_adapter("telegram", "Telegram")
class TelegramAdapter(BasePlatformAdapter):
    pass
```

**注册表**:
- `platform_registry: List[PlatformMetadata]`
- `platform_cls_map: Dict[str, Type]`

**注册的平台** (8个):
1. QQ (OneBot V11)
2. Telegram
3. Discord
4. KOOK
5. Lark (飞书)
6. QQ频道
7. Slack
8. 企业微信

---

### 2.3 Pipeline Stage注册装饰器

**模块**: `packages/core/pipeline/stage.py`

**装饰器**: `@register_stage(priority=int)`

**使用示例**:
```python
@register_stage(priority=10)
class WakingCheckStage(Stage):
    async def process(self, event, ctx):
        pass

@register_stage(priority=100)
class RespondStage(Stage):
    async def process(self, event, ctx):
        pass
```

**注册的Stage** (12个):
1. WakingCheckStage - 唤醒检查
2. WhitelistCheckStage - 白名单检查
3. SessionStatusCheckStage - 会话状态检查
4. ContentSafetyCheckStage - 内容安全检查
5. PreprocessStage - 预处理
6. ProcessStage - 处理
7. RAGEnhanceStage - RAG增强
8. RateLimitStage - 限流
9. SessionSummaryStage - 会话摘要
10. RespondStage - 响应
11. ResultDecorateStage - 结果装饰
12. EventStopper - 事件停止

**特点**:
- 支持优先级排序
- 支持洋葱模型（AsyncGenerator）
- 支持简化模式（返回None）

---

### 2.4 工具注册装饰器

**模块**: `packages/agent/tools/registry.py`

**装饰器**: `@register_tool()`

**使用示例**:
```python
@register_tool(name="calculator", description="计算器")
class CalculatorTool(BaseTool):
    pass
```

**注册表**:
- `_tools: Dict[str, BaseTool]`
- `_tools_by_type: Dict[str, List[BaseTool]]`
- `_agent_assignments: Dict[str, List[str]]`

---

### 2.5 命令注册装饰器

**模块**: `packages/core/command_management.py`

**装饰器**: `@register()`

**使用示例**:
```python
@register("help", "显示帮助")
async def help_command(event):
    pass
```

**注册表**:
- `_command_registry: Dict[str, CommandDescriptor]`

---

### 2.6 备份项注册装饰器（新增）

**模块**: `packages/core/backup/config.py`

**装饰器**: `@BackupRegistry.register(name, description, priority)`

**使用示例**:
```python
@BackupRegistry.register("main_database", "主数据库", priority=10)
async def export_main_database(backup_dir, context):
    pass

@BackupRegistry.register("main_database", "主数据库", priority=10)
async def import_main_database(backup_dir, context):
    pass
```

**注册的备份项** (14个):
1. main_database - 主数据库（导出+导入）
2. config_files - 配置文件（导出+导入）
3. plugins - 插件目录（导出+导入）
4. plugin_data - 插件数据（导出+导入）
5. conversations - 对话目录（导出+导入）
6. attachments - 附件（导出）
7. knowledge_base - 知识库（导出+导入）
8. temp - 临时文件（导出+导入）
9. logs - 日志（导出+导入）

**特点**:
- 支持优先级排序
- 支持启用/禁用
- 分离导出/导入函数

---

## 三、通用装饰器详解

### 3.1 错误处理装饰器

**模块**: `packages/common/decorators.py`

#### @handle_route_errors()
```python
@handle_route_errors("创建备份")
async def create_backup():
    pass
```

**功能**:
- 捕获 ValueError
- 捕获通用 Exception
- 记录日志
- 返回统一的错误响应

#### @handle_async_errors()
```python
@handle_async_errors(operation_name="导入数据")
async def import_data():
    pass
```

**功能**:
- 捕获 Exception
- 记录错误日志
- 返回默认值

---

### 3.2 请求验证装饰器

#### @validate_request_data()
```python
@validate_request_data(required_fields=["name", "description"])
async def create_item():
    pass
```

**功能**:
- 验证必填字段
- 自动获取请求数据
- 返回验证错误

---

### 3.3 缓存装饰器

#### @cache_result()
```python
@cache_result(ttl=300)  # 缓存5分钟
async def expensive_operation():
    pass
```

**功能**:
- 内存缓存
- 支持TTL过期
- 基于函数名、参数、kwargs生成缓存键

---

## 四、装饰器设计模式

### 4.1 注册表模式

所有自定义装饰器都遵循"注册表模式"：

```python
# 1. 定义注册表
_registry = {}
_metadata = {}

# 2. 定义装饰器工厂
def register(name, description, priority=0):
    def decorator(cls_or_func):
        # 3. 提取元数据
        metadata = {
            "name": name,
            "description": description,
            "priority": priority,
        }

        # 4. 注册到全局注册表
        _registry[name] = cls_or_func
        _metadata[name] = metadata

        # 5. 返回原类或函数
        return cls_or_func

    return decorator

# 6. 定义查询函数
def get_all_items():
    return sorted(_metadata.values(), key=lambda x: x["priority"])

def get_item(name):
    return _registry.get(name)
```

### 4.2 优先级排序模式

支持优先级排序的装饰器：
- `@register_stage(priority=int)`
- `@BackupRegistry.register(name, desc, priority=int)`

**实现**:
```python
def get_all_items():
    return sorted(
        _registry.values(),
        key=lambda x: x.priority
    )
```

---

## 五、架构优势

### 5.1 松耦合
- 组件通过装饰器注册，无需手动调用注册代码
- 核心系统不感知具体实现，只依赖接口

### 5.2 可扩展
- 添加新功能只需添加装饰器
- 插件系统天然支持，插件开发者使用相同的装饰器

### 5.3 声明式
- 装饰器让配置更直观
- 代码即配置，无需额外配置文件

### 5.4 类型安全
- 使用 dataclass 定义元数据
- 完整的类型提示

### 5.5 自动发现
- 通过注册表自动发现所有组件
- 支持动态加载和热重载

---

## 六、装饰器使用统计

### 按模块分布

| 模块 | 装饰器数量 | 主要装饰器 |
|------|-----------|-----------|
| provider/ | 40+ | @register_*_provider |
| platform/ | 8+ | @register_platform_adapter |
| core/pipeline/ | 12+ | @register_stage |
| core/backup/ | 14+ | @BackupRegistry.register |
| agent/ | 5+ | @register_tool |
| core/command_management/ | 5+ | @register |
| routes/ | 30+ | @app.get/post, @handle_route_errors |

### 按类型分布

| 类型 | 数量 | 占比 |
|------|------|------|
| 注册装饰器 | 80+ | 40% |
| dataclass | 50+ | 25% |
| 路由装饰器 | 30+ | 15% |
| 通用装饰器 | 20+ | 10% |
| 其他 | 20+ | 10% |

---

## 七、最佳实践

### 7.1 统一的命名约定

```python
# 注册装饰器
@register_XXX(name, description)

# 错误处理装饰器
@handle_XXX_errors(operation_name)

# 验证装饰器
@validate_XXX_data(required_fields=[])
```

### 7.2 完整的类型提示

```python
from typing import Type, Callable, Optional, Dict, Any

def register_item(name: str) -> Callable[[Type], Type]:
    def decorator(cls: Type) -> Type:
        _registry[name] = cls
        return cls
    return decorator
```

### 7.3 支持元数据

```python
@dataclass
class ItemMetadata:
    name: str
    description: str
    priority: int = 0
    enabled: bool = True
```

### 7.4 提供查询接口

```python
def get_all_items() -> List[ItemMetadata]:
    pass

def get_item(name: str) -> Optional[Item]:
    pass

def enable_item(name: str) -> bool:
    pass

def disable_item(name: str) -> bool:
    pass
```

---

## 八、备份系统的装饰器实现

### 8.1 BackupRegistry设计

```python
class BackupRegistry:
    _items: Dict[str, BackupItem] = {}

    @classmethod
    def register(cls, name: str, description: str = "", priority: int = 0):
        def decorator(func):
            item = BackupItem(
                name=name,
                description=description,
                priority=priority,
            )

            if func.__name__.startswith("export_"):
                item.export_func = func
            elif func.__name__.startswith("import_"):
                item.import_func = func

            cls._items[name] = item
            return func
        return decorator

    @classmethod
    def get_all_items(cls) -> List[BackupItem]:
        return sorted(cls._items.values(), key=lambda x: x.priority)
```

### 8.2 使用示例

```python
# 定义备份项
@BackupRegistry.register("main_database", "主数据库", priority=10)
async def export_main_database(backup_dir, context):
    """导出主数据库"""
    pass

@BackupRegistry.register("main_database", "主数据库", priority=10)
async def import_main_database(backup_dir, context):
    """导入主数据库"""
    pass

# 获取所有备份项
items = BackupRegistry.get_all_items()
for item in items:
    print(f"{item.name} - {item.description}")

# 执行导出
executor = BackupExecutor(context)
results = await executor.export()
```

---

## 九、总结

NekoBot 项目大量使用装饰器，是一个**声明式编程**的典范。核心特点：

1. **注册表无处不在** - Provider、Platform、Stage、Tool、Command、Backup
2. **统一的设计模式** - 所有注册装饰器遵循相同的模式
3. **支持优先级** - Stage和Backup支持优先级排序
4. **插件友好** - 装饰器天然支持插件系统
5. **自动发现** - 通过注册表自动发现所有组件
6. **类型安全** - 完整的类型提示和dataclass
7. **松耦合** - 组件通过装饰器注册，无需手动注册
8. **可扩展** - 添加新功能只需添加装饰器

新添加的备份系统完全遵循这一设计模式，与项目整体架构完美融合！
