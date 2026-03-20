# AI 指令系统接入指南 (AI Instruction System Guide)

本系统允许 AI 通过调用指定的 API 指令自主操作电路模拟器。您可以将以下内容作为 System Prompt 提供给您的 AI 模型。

## 1. 接入方式
### 方式 A: 直接调用 API (后台接入)
API 基础路径: `http://localhost:5000/api/ai`
执行指令接口: `POST /execute`

### 方式 B: 通过聊天窗口 (用户交互)
项目界面右下角已新增聊天窗口。用户发送的消息将通过 `/api/chat` 接口处理。您可以在 `app.py` 的 `chat()` 函数中接入 LLM，将用户文本转换为指令。

## 2. 指令集定义 (JSON 格式)

AI 应发送以下格式的 JSON 数据到 `/execute` 接口：
`{"command": "指令名称", "params": { "参数名": "参数值" }}`

### 可用指令列表：

#### 1. `get_state`
获取当前电路的所有元件和连线状态。
- **参数**: 无
- **返回**: `{"elements": [...], "wires": [...]}`

#### 2. `add_element`
在画布上添加一个逻辑元件。
- **参数**:
  - `type`: 元件类型 (可选值: `AND`, `OR`, `NOT`, `INPUT`, `OUTPUT`)
  - `x`: X 坐标 (建议范围 0-1000)
  - `y`: Y 坐标 (建议范围 0-800)
- **示例**: `{"command": "add_element", "params": {"type": "AND", "x": 100, "y": 200}}`

#### 3. `remove_element`
根据 ID 删除一个元件及其关联的所有导线。
- **参数**:
  - `id`: 元件的唯一 ID
- **示例**: `{"command": "remove_element", "params": {"id": "abcd12345"}}`

#### 4. `add_wire`
连接两个元件的端口。
- **参数**:
  - `from_id`: 起始元件 ID
  - `from_port_idx`: 输出端口索引 (通常为 0)
  - `to_id`: 目标元件 ID
  - `to_port_idx`: 输入端口索引 (0 或 1)
- **示例**: `{"command": "add_wire", "params": {"from_id": "id1", "from_port_idx": 0, "to_id": "id2", "to_port_idx": 0}}`

#### 5. `remove_wire`
删除一根导线。
- **参数**:
  - `id`: 导线的唯一 ID
- **示例**: `{"command": "remove_wire", "params": {"id": "wire_123"}}`

#### 6. `toggle_input`
切换输入元件（INPUT）的开关状态（开/关）。
- **参数**:
  - `id`: INPUT 元件的 ID
- **示例**: `{"command": "toggle_input", "params": {"id": "input_id"}}`

#### 7. `clear_circuit`
清空整个画布。
- **参数**: 无

---

## 3. 建议的 System Prompt (给 AI 使用)

你是一个电路模拟器助手。你可以通过调用 API 指令来帮助用户构建和调试逻辑电路。
你可以使用的元件包括：与门(AND)、或门(OR)、非门(NOT)、输入源(INPUT)和输出端(OUTPUT)。

你的工作流程：
1. 首先调用 `get_state` 了解当前电路布局。
2. 根据用户的文本需求（例如 "帮我建一个半加器" 或 "连接这两个门"），分析并生成一系列指令。
3. 自主调用指令直到完成任务。

请确保坐标布局合理，避免元件重叠。
每条指令执行后，前端界面会自动同步并显示最新的电路图。
