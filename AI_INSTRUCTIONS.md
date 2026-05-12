# AI 指令系统接入指南

本系统允许 AI 通过调用指定的 API 指令自主操作电路模拟器。以下内容可作为 System Prompt 提供给您的 AI 模型。

---

## 1. 接入方式

### 方式 A：API 直接调用（后台接入）
- API 基础路径：`http://localhost:5000/api/ai`
- 执行指令：`POST /execute`

### 方式 B：聊天窗口（推荐）
项目右下角的聊天窗口通过 `/api/chat` 处理，AI 以流式 SSE 方式输出。系统已内置完整的自治执行循环。

---

## 2. 指令集

AI 输出以 `<commands>` 和 `</commands>` 标签包裹，每行一条指令。

### 2.1 两种输出格式

系统同时支持传统文本格式和 JSON 格式。可以在同一 `<commands>` 块中混用。

**传统文本格式 (向后兼容):**
```
ADD AND 240 60 g1
WIRE g1 0 g2 1
```

**JSON 格式 (推荐，解析更稳定):**
```json
{"tool": "add_element", "params": {"type": "AND", "x": 240, "y": 60, "alias": "g1"}}
{"tool": "add_wire", "params": {"from_ref": "g1", "from_port_idx": 0, "to_ref": "g2", "to_port_idx": 1}}
```

### 2.2 工具列表

| 工具名 | 文本格式 | JSON 示例 | 说明 |
|--------|----------|-----------|------|
| add_element | `ADD <type> <x> <y> [alias]` | `{"tool":"add_element","params":{"type":"AND","x":240,"y":60,"alias":"g1"}}` | 添加元件。type: AND/OR/NOT/INPUT/OUTPUT/FUNCTION |
| add_wire | `WIRE <from> <idx> <to> <idx>` | `{"tool":"add_wire","params":{"from_ref":"g1","from_port_idx":0,"to_ref":"g2","to_port_idx":1}}` | 连接端口（索引从 0 开始） |
| move_element | `MOVE <id> <x> <y>` | `{"tool":"move_element","params":{"id":"abc123","x":300,"y":100}}` | 移动元件位置 |
| remove_element | `DEL <id>` | `{"tool":"remove_element","params":{"id":"abc123"}}` | 删除元件及关联导线 |
| remove_wire | `DELW <id>` | `{"tool":"remove_wire","params":{"id":"wire123"}}` | 删除单根导线 |
| clear_circuit | `CLEAR` | `{"tool":"clear_circuit","params":{}}` | 清空画布 |
| toggle_input | `TOGGLE <id>` | `{"tool":"toggle_input","params":{"id":"input1"}}` | 切换 INPUT 电平 |
| set_input | `SET <id> <0\|1>` | `{"tool":"set_input","params":{"id":"A","value":1}}` | 设置 INPUT 为指定电平 |
| simulate | `SIM` | `{"tool":"simulate","params":{}}` | 显式触发仿真 |
| sample_outputs | `SAMPLE [id ...]` | `{"tool":"sample_outputs","params":{"ids":["SUM","CARRY"]}}` | 采样 OUTPUT 状态 |
| define_function | `DEFINE_FUNC <name>` | `{"tool":"define_function","params":{"name":"HalfAdder"}}` | 将当前电路封装为函数 |
| set_element_comment | `COMMENT <id> <text>` | `{"tool":"set_element_comment","params":{"id":"and1","comment":"A与B相与"}}` | 设置元件注释 |

### 2.3 别名系统

- ADD 时 alias 参数持久化保存
- 后续所有引用位置都可直接使用 alias
- 支持大小写匹配及 `$` 前缀引用

---

## 3. 反馈系统（v2）

系统不再每轮注入完整电路状态。从第 2 轮开始，仅注入**差异反馈**：

```
--- 本轮操作反馈 ---
执行: 5/5 条命令成功
新增元件 (2):
  + AND abc123 (g1) @ [240, 60]
  + OR def456 (g2) @ [240, 140]
新增连线 (1):
  + abc123 -> def456
当前 IO: 输入: A=0, B=1 | 输出: SUM=1, CARRY=0
```

首轮仍提供全量电路状态以便 AI 了解全局。后续轮次仅反馈变化，大幅减少 token 消耗。

---

## 4. 验证框架

AI 可在输出中包含 `<observe>` 块定义测试用例，系统自动执行并反馈结果（向后兼容 `<verify>` 标签）。

**AI 输出:**
```xml
<observe>
{"cases":[
  {"inputs":[{"id":"A","value":0},{"id":"B","value":1}],
   "expect":[{"id":"SUM","value":1},{"id":"CARRY","value":0}]}
]}
</observe>
```

**系统自动执行后，反馈给下一轮:**
```
--- 测试验证结果 ---
✅ 测试 1: 通过
  ✅ SUM: 期望=1, 实际=1
  ✅ CARRY: 期望=0, 实际=0
```

验证过程使用快照机制：系统先深拷贝当前电路状态，执行测试后自动恢复，不污染用户电路。

---

## 5. 五阶段循环（5-Mode Loop）

这是当前系统的核心设计。每轮循环中，AI 必须依次输出 5 个阶段的内容：

### 5.1 阶段概述

| 阶段 | 标签 | 作用 | 持久化 |
|------|------|------|--------|
| **Think** | `<think>` | 分析用户需求、计划文件、摘要、观察结果 | 不持久化 |
| **Plan** | `<plan>` | 创建/修改 TODO 列表 | 保存到 `plan.md` |
| **Build** | `<build>` | 执行电路构建指令 | 不持久化（执行） |
| **Observe** | `<observe>` | 定义测试用例验证电路 | 不持久化（执行） |
| **Sum** | `<sum>` | 压缩成果和状态为总结 | 保存到 `summary.md` |

### 5.2 每轮输出格式

```xml
<think>
综合分析：用户需求、plan.md 中的 TODO、summary.md 的历史进展、
上一轮观察结果、当前电路状态。明确本轮目标与关键假设。
</think>
<plan>
# Plan
## Objective
[目标]
## Tasks
- [ ] 步骤 1
- [x] 已完成步骤
</plan>
<build>
ADD AND 240 60 g1
WIRE A 0 g1 1
</build>
<observe>
{"cases":[{"inputs":[{"id":"A","value":0},{"id":"B","value":1}],"expect":[{"id":"SUM","value":1}]}]}
</observe>
<sum>
# Summary
## State
[电路状态摘要]
## Progress
[进展]
## Issues
[问题]
</sum>
<answer>
给用户的简短中文说明
</answer>
<done>true 或 false</done>
```

### 5.3 文件持久化

- **plan.md**: 每次 `<plan>` 输出会覆盖保存。包含当前目标、TODO 列表。
- **summary.md**: 每次 `<sum>` 输出会覆盖保存。包含电路状态摘要、进展、问题。
- 这两个文件在每次 circuit 模式启动时自动加载，实现跨会话连续性。

### 5.4 循环控制

- 每次 `<sum>` 后，系统检查 `<done>` 标记
- `done=true` → 目标完成，退出循环
- `done=false` → 继续下一轮（Think 重新分析）
- 自动检测停滞（状态无变化超过 N 轮）和震荡（ABAB 循环）并终止

---

## 6. 函数系统

1. 搭建包含 INPUT 和 OUTPUT 的子电路
2. `DEFINE_FUNC <name>` 封装为函数
3. 系统自动验证或手动 `SET+SAMPLE` 验证
4. `CLEAR` 清空画布
5. `ADD <name>` 复用函数

函数支持多层嵌套（递归深度上限 10 层）。

---

## 7. 自治执行流程

1. **分类**：系统先对用户消息做快速分类（circuit / chat）
2. **circuit 模式** 进入五阶段循环（Think → Plan → Build → Observe → Sum）：
   - 启动时加载 plan.md 和 summary.md（跨会话恢复）
   - 首轮：读取电路状态，构建含全量状态的 system prompt + plan/summary 上下文
   - 后续轮：仅注入上一轮的操作反馈 + state diff + 验证结果
   - AI 流式输出 5 个阶段，系统并行处理：
     - `<think>`：显示给用户
     - `<plan>`：保存到 plan.md
     - `<build>`：实时逐条执行命令（支持 JSON 和文本两种格式），刷新前端画布
     - `<observe>`：自动运行测试用例，结果注入下一轮
     - `<sum>`：保存到 summary.md
   - 每轮完成后检查 `<done>` 决定是否继续
   - 状态无变化超过 N 轮或检测到震荡则自动停止
   - 验证失败或命令出错 → 强制 done=false，要求 AI 修复
3. **chat 模式** 直接单次回复，不进循环
