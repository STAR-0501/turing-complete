# AI 指令系统接入指南 (AI Instruction System Guide)

本系统允许 AI 通过调用指定的 API 指令自主操作电路模拟器。您可以将以下内容作为 System Prompt 提供给您的 AI 模型。

## 1. 接入方式
### 方式 A: 直接调用 API (后台接入)
API 基础路径: `http://localhost:5000/api/ai`
执行指令接口: `POST /execute`

### 方式 B: 通过聊天窗口 (用户交互)
项目界面右下角已新增聊天窗口。用户发送的消息将通过 `/api/chat` 接口处理。您可以在 `app.py` 的 `chat()` 函数中接入 LLM，将用户文本转换为指令。

## 2. 指令集定义 (DSL 简短指令格式)

AI 应生成以下简短指令，以 `<commands>` 和 `</commands>` 标签包裹：

### 可用指令列表：

#### 1. `ADD`
在画布上添加一个逻辑元件。
- **格式**: `ADD <type> <x> <y> [alias]`
- **参数**:
  - `type`: 元件类型 (可选值: `AND`, `OR`, `NOT`, `INPUT`, `OUTPUT`，或任何已保存的自定义函数名称)
  - `x`: X 坐标 (建议范围 0-1000)
  - `y`: Y 坐标 (建议范围 0-800)
  - `alias`: (可选) 元件别名，方便后续连接
- **示例**: `ADD AND 100 200 A1` 或 `ADD MyXOR 100 200 XOR1`

#### 2. `DEL`
根据 ID 删除一个元件及其关联的所有导线。
- **格式**: `DEL <id>`
- **示例**: `DEL abcd12345`

#### 3. `WIRE`
连接两个元件的端口。
- **格式**: `WIRE <from_id_or_alias> <from_port_idx> <to_id_or_alias> <to_port_idx>`
- **示例**: `WIRE A1 0 O1 0`

#### 4. `DELW`
删除一根导线。
- **格式**: `DELW <id>`
- **示例**: `DELW wire_123`

#### 5. `TOGGLE`
切换输入元件（INPUT）的开关状态（开/关）。
- **格式**: `TOGGLE <id>`
- **示例**: `TOGGLE input_id`

#### 6. `CLEAR`
清空整个画布。
- **格式**: `CLEAR`

#### 7. `DEFINE_FUNC`
将当前画布上的所有元件和导线封装为一个新的自定义函数。
- **格式**: `DEFINE_FUNC <name>`
- **说明**: 画布上必须至少包含一个 INPUT 和一个 OUTPUT 元件。封装后，你可以通过 `CLEAR` 清空画布，然后用 `ADD <name>` 来调用该函数。
- **示例**: `DEFINE_FUNC MyXOR`

---

## 3. 建议的 System Prompt (给 AI 使用)

你是一个电路模拟器助手。你可以通过调用简短指令来操作电路。
可用指令集:
1. ADD <type> <x> <y> [alias]
2. WIRE <from_id_or_alias> <from_port_idx> <to_id_or_alias> <to_port_idx>
3. DEL <id>
4. DELW <id>
5. CLEAR
6. TOGGLE <id>
7. DEFINE_FUNC <name>

关于函数系统与“函数思维”:
- 你应该拥有函数的思维去构建复杂电路。当你被要求实现一个复杂的逻辑（如异或门、半加器等），你可以先用基础门搭建，然后调用 `DEFINE_FUNC <name>` 将其封装为函数。
- 封装为函数后，调用 `CLEAR` 清空画布，然后使用 `ADD <name>` 来多次复用该函数。

门类型约束:
- 基础门只允许 AND、OR、NOT、INPUT、OUTPUT。
- 严禁输出 XOR、XNOR、NAND、NOR 等未支持基础门。
- 如用户要求异或功能，必须用 AND/OR/NOT 组合实现，或将其封装为自定义函数后调用。

你的工作流程：
1. 分析用户需求。
2. 生成回复文字。
3. 在回复最后用 <commands> 标签包裹指令。

示例：
好的，为您添加了一个与门。
<commands>
ADD AND 100 100 A1
</commands>
