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

### 基础指令

| 指令 | 格式 | 说明 |
|------|------|------|
| ADD | `ADD <type> <x> <y> [alias]` | 添加元件。type: AND/OR/NOT/INPUT/OUTPUT 或自定义函数名 |
| DEL | `DEL <id_or_alias>` | 删除元件及其关联导线 |
| WIRE | `WIRE <from> <from_port> <to> <to_port>` | 连接端口（端口索引从 0 开始） |
| DELW | `DELW <wire_id>` | 删除单根导线 |
| TOGGLE | `TOGGLE <id_or_alias>` | 切换 INPUT 电平 |
| SET | `SET <id_or_alias> <0\|1>` | 设置 INPUT 为指定电平 |
| SIM | `SIM` | 显式触发仿真 |
| SAMPLE | `SAMPLE [id_or_alias ...]` | 采样 OUTPUT 状态 |
| MOVE | `MOVE <id_or_alias> <x> <y>` | 移动元件位置 |
| CLEAR | `CLEAR` | 清空画布 |
| DEFINE_FUNC | `DEFINE_FUNC <name>` | 将当前电路封装为自定义函数 |
| COMMENT | `COMMENT <id_or_alias> <text>` | 设置元件注释 |

### 别名系统

- ADD 时第 5 个参数为 alias，持久化保存
- 后续所有需要 `<id_or_alias>` 的地方都可直接使用 alias
- 支持大小写匹配

---

## 3. 系统 Prompt 建议

```
你是一个电路模拟器自治执行助手。你不仅要生成指令，还要在每轮执行后检查结果并决定是否继续整改。

可用指令集（每行一条）：
1. ADD <type> <x> <y> [alias]
2. WIRE <from_id_or_alias> <from_port_idx> <to_id_or_alias> <to_port_idx>
3. MOVE <id_or_alias> <x> <y>
4. DEL <id_or_alias>
5. DELW <wire_id>
6. CLEAR
7. TOGGLE <id_or_alias>
8. DEFINE_FUNC <name>
9. SET <id_or_alias> <0|1>
10. SIM
11. SAMPLE [id_or_alias ...]
12. COMMENT <id_or_alias> <text>

规则：
- 基础门只允许 AND、OR、NOT、INPUT、OUTPUT
- 必须使用函数思维：搭建 -> DEFINE_FUNC -> SET+SAMPLE 验证 -> CLEAR -> 复用
- 每轮最多 30 条命令，超出自动截断
- 坐标规则：输入 x=80，门 x=240，输出 x=560，y 间距 80
- <plan> 不超过 80 字，只写做什么 + 坐标策略
- 用 SET+SAMPLE 验证，失败则继续整改

输出结构：
<plan>...</plan>
<answer>...</answer>
<commands>...</commands>
<verify>可选测试用例</verify>
<done>true/false</done>
```

---

## 4. 函数系统

1. 搭建包含 INPUT 和 OUTPUT 的子电路
2. `DEFINE_FUNC <name>` 封装为函数
3. `SET+SAMPLE` 验证函数功能正确
4. `CLEAR` 清空画布
5. `ADD <name>` 复用函数

函数支持多层嵌套（递归深度上限 10 层）。

---

## 5. 自治执行流程

1. 系统先对用户消息做快速分类（circuit / chat）
2. circuit 模式进入多轮循环：
   - 读取电路状态，构建 system prompt
   - LLM 流式输出，系统实时解析 `<commands>` 逐条执行
   - 每执行一条指令刷新前端画布
   - 执行完后检查：状态变化、错误、验证用例
   - 状态无变化超过 N 轮或检测到震荡则自动停止
   - 验证失败或命令出错 → 强制 done=false，要求 AI 修复
3. chat 模式直接单次回复，不进循环
