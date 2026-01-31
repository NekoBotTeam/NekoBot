# 命令冲突解决功能文档

## 功能概述

当两个或多个插件注册了相同的命令名时，系统会检测到冲突并反馈给前端。用户可以选择解决策略，系统会自动应用解决方案。

---

## 工作流程

### 1. 冲突检测

系统在以下时机检测冲突：
- 插件加载时
- 命令注册时
- 手动触发检测

### 2. 冲突反馈

API返回冲突信息：

```json
{
  "conflict_key": "help",
  "handlers": [
    {
      "handler_full_name": "plugin_a:help_handler",
      "handler_name": "help_handler",
      "plugin_name": "plugin_a",
      "plugin_display_name": "插件A",
      "current_name": "help",
      "description": "显示帮助信息",
      "original_command": "help",
      "aliases": [],
      "reserved": false
    },
    {
      "handler_full_name": "plugin_b:help_handler",
      "handler_name": "help_handler",
      "plugin_name": "plugin_b",
      "plugin_name": "plugin_display_name": "插件B",
      "current_name": "help",
      "description": "帮助系统",
      "original_command": "help",
      "aliases": [],
      "reserved": false
    }
  ],
  "available_strategies": [
    {
      "strategy": "keep_first",
      "name": "保留第一个命令，第二个命令使用别名",
      "description": "第一个插件保留 'help' 命令名，第二个插件使用别名"
    },
    {
      "strategy": "keep_second",
      "name": "保留第二个命令，第一个命令使用别名",
      "description": "第二个插件保留 'help' 命令名，第一个插件使用别名"
    },
    {
      "strategy": "alias_first",
      "name": "两个命令都使用别名（第一个）",
      "description": "两个插件都使用别名，第一个插件添加 'help_alias1' 前缀"
    },
    {
      "strategy": "alias_second",
      "name": "两个命令都使用别名（第二个）",
      "description": "两个插件都使用别名，第二个插件添加 'help_alias2' 前缀"
    }
  ]
}
```

### 3. 解决策略

#### keep_first（保留第一个）
- 插件A保留原始命令名 `help`
- 插件B使用别名 `help_alias_plugin_b`

示例：
```json
{
  "conflict_key": "help",
  "resolution_strategy": "keep_first",
  "keep_handler_full_name": "plugin_a:help_handler",
  "resolved_command": "help",
  "note": "保留第一个命令 'help'，第二个命令使用别名",
  "handlers": [
    {
      "handler_full_name": "plugin_a:help_handler",
      "effective_command": "help",
      "aliases": []
    },
    {
      "handler_full_name": "plugin_b:help_handler",
      "effective_command": "help_alias_plugin_b",
      "aliases": ["help_alias_plugin_b"]
    }
  ]
}
```

#### keep_second（保留第二个）
- 插件B保留原始命令名 `help`
- 插件A使用别名 `help_alias_plugin_a`

#### alias_first（第一个使用别名）
- 两个插件都使用别名
- 插件A: `help_alias1`
- 插件B: `help`

示例：
```json
{
  "conflict_key": "help",
  "resolution_strategy": "alias_first",
  "keep_handler_full_name": "plugin_a:help_handler",
  "resolved_command": "help_alias1",
  "note": "两个命令都使用别名，第一个命令",
  "handlers": [
    {
      "handler_full_name": "plugin_a:help_handler",
      "effective_command": "help_alias1",
      "aliases": ["help_alias1"]
    },
    {
      "handler_full_name": "plugin_b:help_handler",
      "effective_command": "help",
      "aliases": []
    }
  ]
}
```

#### alias_second（第二个使用别名）
- 两个插件都使用别名
- 插件A: `help`
- 插件B: `help_alias2`

---

## API 接口

### 列出所有冲突
```
GET /api/commands/conflicts
```

### 获取冲突详情
```
GET /api/commands/conflicts/{conflict_key}
```

### 解决冲突
```
POST /api/commands/conflicts/{conflict_key}/resolve

{
  "resolution_strategy": "keep_first",
  "keep_handler_full_name": "plugin_a:help_handler"
}
```

### 清除已解决的冲突记录
```
DELETE /api/commands/conflicts
```

---

## 数据库模型

### command_configs 表
存储命令配置：
- `handler_full_name`: 处理器完整名称
- `original_command`: 原始命令名
- `resolved_command`: 解决后的命令名
- `enabled`: 是否启用
- `aliases`: 别名列表（JSON）
- `keep_original_alias`: 是否保留原始命令
- `conflict_key`: 冲突键
- `resolution_strategy`: 解决策略
- `note`: 备注
- `extra_data`: 额外数据（JSON）

### command_conflicts 表
跟踪命令冲突：
- `conflict_key`: 冲突键
- `handler_full_name`: 处理器完整名称
- `plugin_name`: 插件名称
- `status`: 状态（pending/resolving/resolved）
- `resolution`: 解决方案
- `resolved_command`: 解决后的命令
- `note`: 备注
- `auto_generated`: 是否自动生成
- `created_at`: 创建时间
- `updated_at`: 更新时间

---

## 前端交互示例

### 1. 检测冲突
```javascript
// 获取所有冲突
const response = await fetch('/api/commands/conflicts');
const conflicts = await response.json();

for (const conflict of conflicts.data) {
  console.log(`冲突: ${conflict.conflict_key}`);
  console.log(`涉及插件: ${conflict.handlers.map(h => h.plugin_display_name).join(', ')}`);
}
```

### 2. 显示冲突详情
```javascript
const conflict = await fetch(`/api/commands/conflicts/${conflict_key}`);
const conflictData = await conflict.json();

console.log('冲突详情:', conflictData.data);
console.log('可用策略:', conflictData.data.available_strategies);
```

### 3. 选择解决策略
```javascript
const resolution = await fetch(
  `/api/commands/conflicts/${conflict_key}/resolve`,
  {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      resolution_strategy: 'keep_first',
      keep_handler_full_name: 'plugin_a:help_handler'
    })
  }
);

const result = await resolution.json();
console.log('解决结果:', result.data);
```

---

## 冲突解决状态

### pending（待处理）
- 冲突已检测，等待用户选择解决方案

### resolving（正在处理）
- 正在应用解决方案

### resolved（已解决）
- 冲突已解决，命令可以正常使用

### ignored（已忽略）
- 用户选择忽略冲突，两个命令都被禁用

---

## 使用场景

### 场景1：新插件与现有插件冲突
1. 加载新插件
2. 检测到命令冲突
3. 用户选择解决策略
4. 自动应用解决方案
5. 新插件正常使用别名

### 场景2：用户手动检测
1. 用户通过WebUI查看所有命令
2. 发现冲突
3. 选择解决策略
4. 保存设置
5. 重启后生效

### 场景3：插件更新导致冲突
1. 更新插件，新增命令
2. 检测到冲突
3. 用户确认保留哪个命令
4. 系统自动处理

---

## 最佳实践

### 1. 插件开发建议
- 使用唯一且有意义的命令名
- 在插件文档中说明可能存在的命令冲突
- 提供合理的默认别名

### 2. 冲突解决建议
- 保留更核心或更常用的命令
- 添加别名时要考虑可读性
- 在插件更新时注意命令变更

### 3. 用户操作建议
- 定期检查命令冲突
- 优先保留核心插件的命令
- 避免频繁更改冲突解决策略

---

## 与AstrBot的对比

| 功能 | NekoBot | AstrBot |
|------|---------|---------|
| 基础别名支持 | ✅ | ✅ |
| 冲突检测 | ✅ | ✅ |
| 冲突列表 | ✅ | ✅ |
| 冲突解决API | ✅ | ❌ |
| 冲突解决策略 | ✅ | ✅ |
| 冲突状态跟踪 | ✅ | ✅ |
| 冲突解决策略 | 4种 | 4种 |
| 命令组支持 | ❌ | ✅ |
| 配置持久化 | ❌ | ✅ |
| 冲突历史记录 | ❌ | ✅ |

---

## 总结

NekoBot 的命令冲突解决系统提供了：
1. ✅ 完整的冲突检测
2. ✅ 4种解决策略
3. ✅ 冲突状态跟踪
4. ✅ 完整的API接口
5. ✅ 数据库持久化

相比 AstrBot，主要缺少：
- ❌ 命令组支持
- ❌ 配置持久化（重启后配置丢失）
- ❌ 冲突历史记录

建议优先级：
1. **高优先级**: 配置持久化
2. **中优先级**: 命令组支持
3. **低优先级**: 冲突历史记录
