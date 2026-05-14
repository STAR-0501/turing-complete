# 逻辑电路模拟系统 (Turing Complete)

一个基于浏览器的数字逻辑电路模拟器，支持 **手动搭建** 与 **AI 自治搭建**。具备自定义模块封装、多层嵌套、电路模式自学习、自演进知识库等能力。

---

## 一、运行环境

**后端**
- Python 3.6+
- Flask 3.0+
- requests

**前端**
- 现代浏览器（Chrome / Edge / Firefox）

**AI（可选）**
- 兼容 OpenAI API 格式的大模型服务（如 DeepSeek、OpenAI、通义千问等）
- 默认使用 [DeepSeek API](https://platform.deepseek.com/)

---

## 二、快速开始

```bash
# 1. 安装依赖
pip install flask requests

# 2. （可选）配置 AI
#    编辑 app.py，将 AI_CONFIG["api_key"] 改为你的 API Key

# 3. 启动
python app.py

# 4. 打开浏览器访问
http://localhost:5000
```

---

## 三、项目架构

```
turing-complete/
├── app.py                    # Flask 后端：路由、AI 自治循环（5 阶段）、会话管理
├── ai_commands.py            # CircuitManager（电路持久化 + 布尔仿真引擎）
├── circuit_data.json         # 电路持久化文件 (.gitignore)
├── modules_data.json         # 自定义模块持久化文件 (.gitignore)
├── plan.md                   # AI 计划持久化（5 阶段循环）
├── summary.md                # AI 会话摘要持久化
├── skills.md                 # 自演进知识库（AI 自主学习）
├── static/
│   ├── scripts/
│   │   ├── app.js            # 前端主逻辑：拖拽、连线、工具切换、快捷键
│   │   ├── circuit.js        # 前端电路计算引擎（支持递归嵌套模块）
│   │   ├── chat.js           # AI 聊天窗口（流式 SSE + 指令执行 + 轮次展示）
│   │   ├── elements.js       # 元件模板定义
│   │   ├── renderer.js       # Canvas 渲染器
│   │   └── utils.js          # 工具函数
│   └── style/css/styles.css  # 全局样式（赛博朋克风格）
└── templates/index.html      # 单页应用入口
```

### 后端核心模块 (`ai_commands.py`)

| 组件 | 职责 |
|------|------|
| `CircuitManager` | 电路持久化（原子写入）、元件/导线 CRUD |
| `SimulationContext` | 仿真上下文（elements、wires、depth） |
| `_simulate_elements_until_stable` | 迭代仿真直到所有信号稳定 |
| `_calc_and/or/not/output_state` | 各类型元件的状态计算（策略模式） |
| `_calculate_module_element` | 递归计算嵌套模块（深度上限 10） |
| `define_module()` | 将当前电路封装为可复用模块 |
| `known_circuit_patterns` | 预注册电路拓扑模式（HalfAdder、FullAdder） |

### 后端 API 路由 (`app.py`)

| 路由 | 功能 |
|------|------|
| `/api/save-circuit` | 保存电路到文件 |
| `/api/load-circuit` | 从文件加载电路 |
| `/api/ai/execute` | 执行单条电路指令 |
| `/api/ai/generate-comments` | AI 自动为元件生成中文注释 |
| `/api/ai/generate-layout` | AI 自动整理电路布局 |
| `/api/ai/generate-circuit` | 根据自然语言需求生成完整电路 |
| `/api/chat` | **AI 自治执行入口**（流式 SSE） |
| `/api/save-module` | 保存单个自定义模块 |
| `/api/save-modules` | 批量保存模块列表 |
| `/api/load-modules` | 加载模块列表 |

---

## 四、AI 自治执行模式

> AI 像写代码的 Agent 一样，**多轮计划→执行→检查→迭代** 直到完成。

### 工作流

1. **快速分类**：先判断用户意图是 `circuit`（需要电路操作）还是 `chat`（日常对话）
2. **chat 模式**：直接单次 LLM 调用回复，不进自治循环
3. **circuit 模式**：进入多轮循环：
   - 每轮读取当前电路状态，构建 system prompt
   - LLM 输出 `<think> <plan> <build> <verify> <done>` 五阶段标签结构
   - 流式接收时**逐条实时执行**指令，每执行一条刷新画布
   - 执行完后自动检查：状态变化、错误、验证用例
   - 声明 `done=true` 后，系统自动检测电路拓扑模式并注册为模块
   - 如果未完成且未出错，继续下一轮

### 五阶段标签

| 标签 | 用途 |
|------|------|
| `<think>` | 分析需求、拆解步骤 |
| `<plan>` | 输出具体搭建计划 |
| `<build>` | 输出电路操作指令 |
| `<observe>` | 观察反馈、调整策略 |
| `<sum>` | 总结完成情况 |

### AI 可用指令

| 指令 | 格式 | 说明 |
|------|------|------|
| ADD | `ADD <type> <x> <y> [alias]` | 添加元件（AND/OR/NOT/INPUT/OUTPUT/MODULE） |
| WIRE | `WIRE <from> <from_port> <to> <to_port>` | 连接导线（端口从 0 开始） |
| MOVE | `MOVE <id_or_alias> <x> <y>` | 移动元件 |
| DEL | `DEL <id_or_alias>` | 删除元件 |
| DELW | `DELW <wire_id>` | 删除导线 |
| CLEAR | `CLEAR` | 清空画布 |
| TOGGLE | `TOGGLE <id_or_alias>` | 切换 INPUT 电平 |
| SET | `SET <id_or_alias> <0\|1>` | 设置 INPUT 为指定电平 |
| SIM | `SIM` | 显式触发仿真 |
| SAMPLE | `SAMPLE [id_or_alias ...]` | 采样 OUTPUT 状态 |
| DEFINE_MODULE | `DEFINE_MODULE <name>` | 将当前电路封装为模块 |
| COMMENT | `COMMENT <id_or_alias> <text>` | 设置元件注释 |

> 也支持 JSON 格式指令：`{"cmd": "ADD", "type": "AND", "x": 240, "y": 200, "alias": "a1"}`

### 系统提示词中的引导规则

- **命令上限**：每轮 ≤ 30 条，超出自动截断并提示下轮继续
- **模块思维优先**：复杂逻辑先搭建子电路 → `DEFINE_MODULE` → `SET+SAMPLE` 验证 → `CLEAR` → `ADD MODULE` 复用
- **模式复用**：搭建前优先检查 `skills.md` 中的已知电路模式（如 HalfAdder、FullAdder），先用 `ADD MODULE` 而非从零搭建
- **坐标规则**：输入 x=80、门 x=240、输出 x=560，y 间距 80
- **验证驱动**：每完成子目标用 `SET+SAMPLE` 或 `<verify>` 做测试

---

## 五、电路模式自学习

系统能在 AI 声明 `done=true` 后自动检测已搭建的电路拓扑，匹配已知模式并注册为模块：

| 模式 | 检测逻辑 | 自动操作 |
|------|---------|---------|
| HalfAdder | XOR + AND 共享输入端 | `DEFINE_MODULE HalfAdder` + 更新 skills.md |
| FullAdder | 2×XOR + 2×AND + OR | `DEFINE_MODULE FullAdder` + 更新 skills.md |

检测到的模式同时写入 `skills.md`，后续会话中 AI 可直接使用。

---

## 六、自演进知识库

`skills.md` 是一个由 AI 自主维护的知识库：

- **种子技能**：随项目提供基础调试、架构、前端风格指南
- **自主学习**：AI 每次会话可输出 `<skills>` 块，系统自动提取、去重、持久化
- **去重机制**：按标题（`### Skill-*`）匹配，已存在的技能自动跳过
- **技能注入**：每次 AI 请求时，`skills.md` 内容自动注入 system prompt

---

## 七、手动操作

### 快捷键

| 键 | 功能 |
|----|------|
| 1 | 选择工具 |
| 2 | 输入切换工具 |
| 3 | 添加与门 |
| 4 | 添加或门 |
| 5 | 添加非门 |
| 6 | 添加输入 |
| 7 | 添加输出 |
| 8 | 删除工具 |
| 9 | 清空电路 |
| 0 | 切换网格 |
| Ctrl+Z / Ctrl+Y | 撤销 / 重做 |
| Ctrl+C / Ctrl+V | 复制 / 粘贴 |
| Ctrl+A | 全选 |
| Ctrl+S | 保存为模块 |
| Ctrl+D | 删除选中元件 |
| Esc | 取消操作 |

### 状态颜色

- **绿色**：信号 1
- **红色**：信号 0
- **灰色**：未连接

---

## 八、模块系统

1. 搭建包含 INPUT 和 OUTPUT 的完整子电路
2. 框选所有元件，按 `Ctrl+S` 或使用命令 `DEFINE_MODULE <name>`
3. 右侧面板出现模块名称，点击即可放置
4. 支持多层嵌套：模块内部可调用其他模块
5. 电路模式自学习：AI 声明完成后自动检测常用模式并注册

---

## 九、高级功能

### 深度思考模式

聊天输入框左侧有 **深度思考** 按钮，开启后：
- 后端发送 `reasoning_effort="high"` + 思维链参数
- AI 会先输出思维链再给出最终答案（适合复杂电路设计）

### 自动注释

点击工具栏的 AI 注释按钮，AI 会自动为每个元件生成中文功能说明。

### 自动布局

点击工具栏的 AI 排版按钮，AI 会重新计算所有元件的位置使其布局清晰。

---

## 十、故障排除

| 问题 | 解决方案 |
|------|---------|
| 启动失败 | 检查 Python 版本和依赖安装 |
| 端口占用 | `app.py` 最后一行改 `port=5001` |
| AI 不工作 | 检查 `AI_CONFIG["api_key"]` 和网络连接 |
| 电路不计算 | 检查输入端是否都已连线 |
| 文件损坏 | 删除 `circuit_data.json` 和 `modules_data.json` 重启 |
