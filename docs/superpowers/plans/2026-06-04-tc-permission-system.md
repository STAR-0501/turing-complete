# TC Permission & Role System Implementation Plan

> **机制编号：** 2.3 | **优先级：** P0 | **预估工时：** 0.5 天

## 目标

为 TC 的 AI Agent 添加工具级别的权限检查，在 Agent 执行指令前验证操作权限，防止 Agent 执行越权操作（如删除高价值模块、修改受保护区域）。

## 背景

Opencode 的 `permission.ts` 使用 allow/deny 模式实现工具级权限检查，`agent/subagent-permissions.ts` 定义了子代理的权限继承策略。TC 的 AI Agent 通过 `ai_commands.py` 的 `CircuitManager` 执行指令，目前无任何权限检查——Agent 可以执行任何指令（ADD/DEL/WIRE/MOVE/CLEAR 等），没有操作限制。

## 设计

### 核心思路

在 `ai_commands.py` 的指令执行入口添加可插拔的权限检查层。定义操作权限级别（read/exec/write/admin），为每个指令分配所需级别，在 `CircuitManager` 执行前检查当前 Agent 会话的权限。

### 权限模型

```
Permission 级别（递增）：
  READ    → 读取电路状态、采样输出
  EXEC    → 仿真、切换输入电平（无修改）
  WRITE   → 添加/移动/连线/注释元件
  ADMIN   → 删除元件、清空画布、封装模块
```

### 文件结构

| 文件 | 说明 |
|------|------|
| `permissions.py` | 新增：权限检查核心逻辑 |
| `ai_commands.py` | 修改：在指令执行入口集成权限检查 |

### permissions.py 设计

```python
from enum import IntEnum

class Permission(IntEnum):
    READ = 0
    EXEC = 1
    WRITE = 2
    ADMIN = 3

# 每个工具所需的最小权限
TOOL_PERMISSIONS = {
    "sample_outputs": Permission.READ,
    "get_circuit_info": Permission.READ,

    "simulate": Permission.EXEC,
    "toggle_input": Permission.EXEC,
    "set_input": Permission.EXEC,

    "add_element": Permission.WRITE,
    "add_wire": Permission.WRITE,
    "move_element": Permission.WRITE,
    "set_element_comment": Permission.WRITE,

    "remove_element": Permission.ADMIN,
    "remove_wire": Permission.ADMIN,
    "clear_circuit": Permission.ADMIN,
    "define_module": Permission.ADMIN,
}


class PermissionChecker:
    def __init__(self, level: Permission = Permission.WRITE):
        self.level = level

    def check(self, tool_name: str) -> bool:
        required = TOOL_PERMISSIONS.get(tool_name, Permission.ADMIN)
        return self.level >= required
```

### app.py 集成

在 `CircuitManager` 初始化时传入权限级别：

```python
# 默认 Agent 会话级别
from permissions import PermissionChecker, Permission
perm_checker = PermissionChecker(level=Permission.WRITE)
circuit_mgr = CircuitManager(circuit_data_file, modules_data_file, perm_checker=perm_checker)
```

在 `ai_commands.py` 的每个指令执行方法开头：

```python
def execute(self, tool_name, params):
    if self.perm_checker and not self.perm_checker.check(tool_name):
        return {"error": f"Permission denied: {tool_name} requires {TOOL_PERMISSIONS[tool_name]}, current level is {self.perm_checker.level}"}
    # 原执行逻辑...
```

## 任务分解

- [ ] 1. 创建 `permissions.py` — 定义 Permission 枚举和 TOOL_PERMISSIONS 映射
- [ ] 2. 实现 `PermissionChecker` 类
- [ ] 3. 修改 `ai_commands.py` — 在 `CircuitManager.__init__` 接受可选 `perm_checker`
- [ ] 4. 修改 `ai_commands.py` — 在每个指令执行方法开头插入权限检查
- [ ] 5. 修改 `app.py` — Agent 会话创建时传入权限级别
- [ ] 6. 测试：验证不同权限级别下指令能否正确被允许/拒绝
- [ ] 7. 提交 commit

## 关键决策

- **默认级别**：WRITE（允许读写仿真和添加元件，禁止删除/清除）
- **Admin 访问**：保留在特定场景（用户授权后）提升权限的接口
- **不采用**细粒度资源级权限（如"只能删除某几个特定元件"）— 当前阶段过于复杂
- **错误处理**：权限拒绝时返回结构化错误信息，Agent 据此调整行为
