# 命令别名功能对比分析

## 对比总结

是的！AstrBot 有更完善的命令别名系统。以下是对比：

---

## 一、NekoBot 当前实现

### 1.1 命令描述符

```python
@dataclass
class CommandDescriptor:
    handler_full_name: str = ""
    handler_name: str = ""
    plugin_name: str = ""
    module_path: str = ""
    description: str = ""
    command_type: str = "command"
    original_command: str | None = None
    effective_command: str | None = None
    aliases: List[str] = field(default_factory=list)  # ✅ 支持别名
    permission: str = "everyone"
    enabled: bool = True
    is_group: bool = False
    is_sub_command: bool = False
    reserved: bool = False
    sub_commands: List["CommandDescriptor"] = field(default_factory=list)
```

### 1.2 注册命令

```python
def register_command(
    handler_full_name: str,
    handler_name: str,
    plugin_name: str,
    module_path: str,
    description: str = "",
    aliases: List[str] | None = None,  # ✅ 支持别名
    permission: str = "everyone",
) -> CommandDescriptor:
    descriptor = CommandDescriptor(
        handler_full_name=handler_full_name,
        handler_name=handler_name,
        plugin_name=plugin_name,
        module_path=module_path,
        description=description,
        command_type="command",
        original_command=handler_name,
        effective_command=handler_name,
        aliases=aliases or [],  # ✅ 别名列表
        permission=permission,
        enabled=True,
    )
    _command_registry[handler_full_name] = descriptor
    return descriptor
```

### 1.3 重命名命令（支持别名）

```python
def rename_command(
    handler_full_name: str,
    new_name: str,
    aliases: List[str] | None = None,  # ✅ 支持设置别名
) -> Optional[CommandDescriptor]:
    descriptor = _command_registry.get(handler_full_name)
    if not descriptor:
        return None

    new_name = new_name.strip()
    if not new_name:
        return None

    # 检查命令名是否被占用
    for desc in _command_registry.values():
        if desc.handler_full_name != handler_full_name and (
            desc.effective_command == new_name or new_name in desc.aliases
        ):
            return None

    # 检查别名是否被占用
    if aliases:
        for alias in aliases:
            alias = alias.strip()
            if not alias:
                continue
            for desc in _command_registry.values():
                if desc.handler_full_name != handler_full_name and (
                    desc.effective_command == alias or alias in desc.aliases
                ):
                    return None

    descriptor.effective_command = new_name
    descriptor.aliases = aliases or []
    return descriptor
```

### 1.4 列出命令冲突

```python
def list_command_conflicts() -> List[Dict[str, Any]]:
    """列出所有冲突的命令"""
    conflicts: Dict[str, List[CommandDescriptor]] = {}
    for desc in _command_registry.values():
        if desc.effective_command and desc.enabled:
            if desc.effective_command not in conflicts:
                conflicts[desc.effective_command] = []
            conflicts[desc.effective_command].append(desc)

    details = [
        {
            "conflict_key": key,
            "handlers": [
                {
                    "handler_full_name": item.handler_full_name,
                    "plugin": item.plugin_name,
                    "current_name": item.effective_command,
                }
                for item in group
            ],
        }
        for key, group in conflicts.items()
        if len(group) > 1
    ]
    return details
```

---

## 二、AstrBot 增强功能

### 2.1 命令组支持

```python
@dataclass
class CommandDescriptor:
    # ... NekoBot 已有字段 ...

    # ✅ 新增：命令组支持
    parent_signature: str = ""
    parent_group_handler: str = ""
    raw_command_name: str | None = None
    current_fragment: str | None = None

    # ✅ 新增：保留原始命令
    keep_original_alias: bool = False

    # ✅ 新增：解决策略
    resolution_strategy: str | None = None

    # ✅ 新增：配置绑定
    config: CommandConfig | None = None

    # ✅ 新增：冲突标志
    has_conflict: bool = False
```

### 2.2 命令配置持久化

```python
@dataclass
class CommandConfig(SQLModel, table=True):
    __tablename__ = "command_configs"

    handler_full_name: str = Field(
        max_length=512,
        primary_key=True,
    )
    plugin_name: str = Field(max_length=255, nullable=False)
    module_path: str = Field(max_length=255, nullable=False)
    original_command: str = Field(max_length=255, nullable=False)
    resolved_command: str | None = Field(max_length=255, default=None)
    enabled: bool = Field(default=True, nullable=False)
    keep_original_alias: bool = Field(default=False, nullable=False)  # ✅ 保留原始命令
    conflict_key: str | None = Field(max_length=255, default=None)
    resolution_strategy: str | None = Field(max_length=64, default=None)  # ✅ 解决策略
    note: str | None = Field(sa_type=Text)
    extra_data: dict | None = Field(sa_type=JSON)
    auto_managed: bool = Field(default=False, nullable=False)
    created_at: datetime = ...
    updated_at: datetime = ...
```

### 2.3 命令冲突跟踪

```python
@dataclass
class CommandConflict(SQLModel, table=True):
    """冲突跟踪表"""
    __tablename__ = "command_conflicts"

    id: int | None = Field(...)
    conflict_key: str = Field(nullable=False, max_length=255)
    handler_full_name: str = Field(nullable=False, max_length=512)
    plugin_name: str = Field(nullable=False, max_length=255)
    status: str = Field(default="pending", max_length=32)  # ✅ 冲突状态
    resolution: str | None = Field(max_length=64)  # ✅ 解决方案
    resolved_command: str | None = Field(max_length=255)  # ✅ 解决后的命令
    note: str | None = Field(sa_type=Text)  # ✅ 备注
    extra_data: dict | None = Field(sa_type=JSON)
    auto_generated: bool = Field(default=False)  # ✅ 是否自动生成
    created_at: datetime = ...
    updated_at: datetime = ...
```

### 2.4 命令组合（支持命令组）

```python
def _compose_command(parent_signature: str, fragment: str | None) -> str:
    """组合命令（支持命令组）

    Args:
        parent_signature: 父命令签名（如 "group"）
        fragment: 命令片段（如 "subcmd"）

    Returns:
        组合后的完整命令（如 "group subcmd"）

    Examples:
        >>> _compose_command("group", "subcmd")
        "group subcmd"
        >>> _compose_command("group", None)
        "group"
        >>> _compose_command("", "cmd")
        "cmd"
    """
    fragment = (fragment or "").strip()
    parent_signature = parent_signature.strip()
    if not parent_signature:
        return fragment
    if not fragment:
        return parent_signature
    return f"{parent_signature} {fragment}"
```

### 2.5 命令重命名（支持策略）

```python
async def rename_command(
    handler_full_name: str,
    new_fragment: str,
    aliases: list[str] | None = None,
) -> CommandDescriptor:
    """重命名命令（支持解决策略）

    Args:
        handler_full_name: 处理函数完整名称
        new_fragment: 新命令片段
        aliases: 别名列表

    Returns:
        命令描述符

    Raises:
        ValueError: 命令名或别名被占用

    Features:
        - ✅ 支持命令组（parent_signature）
        - ✅ 支持别名
        - ✅ 冲突检查
        - ✅ 数据库持久化
        - ✅ 解决策略（resolution_strategy）
    """
    # 1. 验证主命令
    candidate_full = _compose_command(descriptor.parent_signature, new_fragment)
    if _is_command_in_use(handler_full_name, candidate_full):
        raise ValueError(f"指令名 '{candidate_full}' 已被其他指令占用。")

    # 2. 验证别名
    if aliases:
        for alias in aliases:
            alias = alias.strip()
            if not alias:
                continue
            alias_full = _compose_command(descriptor.parent_signature, alias)
            if _is_command_in_use(handler_full_name, alias_full):
                raise ValueError(f"别名 '{alias_full}' 已被其他指令占用。")

    # 3. 更新配置（数据库）
    config = await db_helper.upsert_command_config(
        handler_full_name=handler_full_name,
        plugin_name=descriptor.plugin_name or "",
        module_path=descriptor.module_path,
        original_command=descriptor.original_command or descriptor.handler_name,
        resolved_command=new_fragment,
        enabled=True if descriptor.enabled else False,
        keep_original_alias=False,  # ✅ 保留原始命令
        conflict_key=descriptor.original_command,
        resolution_strategy="manual_rename",  # ✅ 解决策略
        note=None,
        extra_data=merged_extra,
        auto_managed=False,
    )

    # 4. 同步配置
    await sync_command_configs()
    return descriptor
```

### 2.6 命令组注册

```python
@filter.command_group("group_name")
async def group_handler(event):
    """命令组处理器"""
    pass

@filter.command("sub_command", alias={"alias1", "alias2"}, parent=group_handler)
async def sub_command_handler(event):
    """子命令处理器"""
    pass
```

---

## 三、功能对比表

| 功能 | NekoBot | AstrBot |
|------|---------|---------|
| 基本别名支持 | ✅ | ✅ |
| 别名冲突检测 | ✅ | ✅ |
| 命令冲突列出 | ✅ | ✅ |
| 命令重命名 | ✅ | ✅ |
| 命令配置持久化 | ❌ | ✅ |
| 命令组支持 | ❌ | ✅ |
| 子命令支持 | ⚠️ 基础 | ✅ 完整 |
| 冲突状态跟踪 | ❌ | ✅ |
| 解决策略 | ❌ | ✅ |
| 保留原始命令 | ❌ | ✅ |
| 数据库表 | ❌ | ✅ CommandConfig |
| 冲突表 | ❌ | ✅ CommandConflict |
| 命令组装饰器 | ❌ | ✅ @filter.command_group |
| 别名装饰器 | ❌ | ✅ @filter.command(..., alias={}) |
| 父命令签名 | ❌ | ✅ parent_signature |
| 自动冲突解决 | ❌ | ✅ auto_generated |

---

## 四、关键差异分析

### 4.1 NekoBot 缺失功能

#### ❌ 命令组系统
```python
# NekoBot 没有
@filter.command_group("admin")
async def admin_group():
    pass

@filter.command("add", parent=admin_group)
async def admin_add():
    pass
```

#### ❌ 配置持久化
```python
# NekoBot: 配置只在内存
_command_registry = {}

# AstrBot: 配置持久化到数据库
CommandConfig(
    handler_full_name="...",
    resolved_command="new_name",
    enabled=True,
    keep_original_alias=False,
    resolution_strategy="manual_rename",
    conflict_key="...",
)
```

#### ❌ 冲突解决策略
```python
# NekoBot: 只能检测冲突
def list_command_conflicts():
    # 返回冲突列表
    pass

# AstrBot: 支持解决策略
CommandConflict(
    status="pending",  # pending/resolved/ignored
    resolution="manual_rename",  # manual_rename/keep_original/auto_rename
    resolved_command="...",
    note="...",
    auto_generated=False,
)
```

### 4.2 AstrBot 独有功能

#### ✅ 1. 命令组装饰器

```python
@filter.command_group("admin", "管理员命令")
async def admin_group(event):
    """管理员命令组"""
    pass

@filter.command("add", "添加用户", parent=admin_group, alias={"create"})
async def admin_add_user(event):
    """添加用户"""
    pass
```

#### ✅ 2. 命令配置数据库

```python
# 创建配置
config = await db_helper.upsert_command_config(
    handler_full_name="...",
    resolved_command="new_name",
    keep_original_alias=True,  # 保留原始命令
    resolution_strategy="keep_original",
    extra_data={"reason": "用户自定义"},
)
```

#### ✅ 3. 冲突跟踪和解决

```python
# 列出所有冲突
conflicts = await db_helper.list_command_conflicts()
for conflict in conflicts:
    print(f"冲突: {conflict.conflict_key}")
    print(f"状态: {conflict.status}")
    print(f"解决方案: {conflict.resolution}")
    print(f"处理函数: {conflict.handler_full_name}")
```

#### ✅ 4. 原始命令保留

```python
# 命令重命名时保留原始命令
config = await db_helper.upsert_command_config(
    keep_original_alias=True,  # ✅ 保留
    resolution_strategy="keep_original",
    resolved_command="new_name",
)
```

---

## 五、建议增强

### 5.1 添加命令组支持

```python
@dataclass
class CommandDescriptor:
    # ... 现有字段 ...

    parent_signature: str = ""  # ✅ 新增
    parent_group_handler: str = ""  # ✅ 新增
    raw_command_name: str | None = None  # ✅ 新增
    current_fragment: str | None = None  # ✅ 新增
```

### 5.2 添加命令组装饰器

```python
def register_command_group(
    handler_full_name: str,
    handler_name: str,
    plugin_name: str,
    module_path: str,
    description: str = "",
) -> CommandDescriptor:
    """注册命令组"""
    descriptor = CommandDescriptor(
        handler_full_name=handler_full_name,
        handler_name=handler_name,
        plugin_name=plugin_name,
        module_path=module_path,
        description=description,
        command_type="group",  # ✅ 新增类型
        is_group=True,  # ✅ 新增
    )
    _command_registry[handler_full_name] = descriptor
    return descriptor
```

### 5.3 添加配置持久化

```python
from packages.core.database import DatabaseManager

class CommandConfigManager:
    """命令配置管理器"""

    def __init__(self, db: DatabaseManager):
        self.db = db

    async def get_command_config(self, handler_full_name: str) -> Optional[dict]:
        """获取命令配置"""
        pass

    async def update_command_config(
        self,
        handler_full_name: str,
        resolved_command: str = None,
        enabled: bool = None,
        aliases: list[str] = None,
        keep_original_alias: bool = None,
        resolution_strategy: str = None,
    ) -> bool:
        """更新命令配置"""
        pass
```

### 5.4 添加冲突跟踪

```python
@dataclass
class CommandConflict:
    """命令冲突记录"""
    conflict_key: str
    handlers: List[CommandDescriptor]
    status: str = "pending"  # pending/resolved/ignored
    resolution: str | None = None
    resolved_command: str | None = None
    note: str | None = None
    auto_generated: bool = False
```

### 5.5 添加解决策略

```python
class ResolutionStrategy:
    """冲突解决策略"""
    MANUAL_RENAME = "manual_rename"  # 手动重命名
    KEEP_ORIGINAL = "keep_original"  # 保留原始命令
    AUTO_RENAME = "auto_rename"  # 自动重命名（加后缀）
    IGNORE = "ignore"  # 忽略冲突
    DISABLE_ALL = "disable_all"  # 禁用所有冲突命令
```

---

## 六、实现建议

### 阶段1: 添加命令组支持

1. 更新 CommandDescriptor
2. 实现 register_command_group
3. 实现子命令注册
4. 更新命令匹配逻辑

### 阶段2: 添加配置持久化

1. 创建 command_configs 表
2. 实现 CommandConfigManager
3. 在注册/重命名时同步配置
4. 重启时加载配置

### 阶段3: 添加冲突跟踪

1. 创建 command_conflicts 表
2. 实现冲突检测和记录
3. 实现冲突解决策略
4. 添加冲突管理API

### 阶段4: 完善装饰器

1. 添加 @filter.command_group()
2. 添加 @filter.command(..., parent=group)
3. 添加 @filter.command(..., alias={...})
4. 支持命令组和子命令

---

## 总结

NekoBot 已经有了基础的命令别名支持，但相比 AstrBot 还缺少：

### ❌ 缺失的核心功能
1. **命令组系统** - 支持多级命令（admin add user）
2. **配置持久化** - 命令配置存储到数据库
3. **冲突跟踪** - 冲突状态和解决历史
4. **解决策略** - 多种冲突处理方式
5. **原始命令保留** - keep_original_alias

### ✅ 已有功能
1. 基本别名支持
2. 别名冲突检测
3. 命令重命名
4. 命令冲突列出

### 🎯 优先级建议
1. **高优先级**: 配置持久化（重启后配置不丢失）
2. **中优先级**: 命令组系统（支持子命令）
3. **低优先级**: 冲突跟踪和解决策略
