# Opencode 研究：TC Agent 电路能力增强方案

> 研究日期：2026-06-04
> 研究目标：分析 [Opencode](https://github.com/opencode-ai/opencode) Agent 机制，提取可直接提升 TC Agent 搭建/调试电路能力的方案。
> 筛选标准：只保留对 **Agent 操作电路**（添加元件、连线、仿真、检测、封装、分析）有直接帮助的机制。SQLite/事件总线/MCP/插件/结构化消息/处理器等「写代码场景」功能已排除。

---

## 一、架构对比（仅相关维度）

| 维度 | OpenCode | TC (Turing Complete) |
|------|----------|----------------------|
| Agent 定义 | Schema-first，类型安全 | `_AI_CONFIG_DEFAULTS` 硬编码 |
| 权限模型 | 工具级 + 会话级权限继承 | 无 |
| 上下文管理 | 自动 compaction + prune + overflow 检测 | 无 |
| 子代理 | 正式 `task()` 工具，权限继承 | 手动 spawn，无权限控制 |
| 技能系统 | URL 发现 + 目录扫描 + 标准化格式 | 单文件 skills.md |
| 重试机制 | 指数退避 + API header 感知 | 无 |
| 指令系统 | 运行时动态注入模板 | 静态 AI_INSTRUCTIONS.md |

---

## 二、直接可用的 7 项机制

### 2.1 上下文管理（Context Compaction + Overflow）← P0

**OpenCode 实现（session/compaction.ts, overflow.ts, config/compaction.ts）：**

```
溢出检测:
  isOverflow(total_tokens, usable_context) → bool
  保留 COMPACTION_BUFFER (20K tokens) 给模型输出

Compaction 策略:
  - 保护最近 2 轮对话不被压缩
  - 保护 skill 工具的输出
  - 保留 session/instruction.ts 注入的指令
  - 中间轮次 → 结构化 Markdown 摘要
    (Goal / Constraints / Progress / Key Decisions / Next Steps)
  - 最旧历史 → 丢弃

配置化参数:
  - auto: boolean         // 是否自动触发
  - keep.rounds: number   // 保留轮次数
  - keep.tokens: number   // 保留令牌数
  - buffer: number        // 输出缓冲区
```

**TC 现状：** 完全无上下文管理。`plan.md` 和 `summary.md` 仅跨会话持久化，不解决单轮对话内的上下文溢出。搭建复杂电路（半加器→全加器→ALU）时历史累积会超出模型上下文窗口。

**改进方案：**
- `_build_autonomous_system_prompt` 中动态裁剪历史：
  - 最近 2 轮完整保留
  - 中间轮次压缩为结构化摘要（Goal/Progress/Blockers/Decisions）
  - 最旧部分丢弃
- `plan.md` 格式结构化：加入 Goal/Progress/Blockers/Decisions 字段
- 可配置参数：`max_context_tokens`、`compaction_strategy`、`protected_tools`

**对电路搭建的价值：** 搭建大型电路（如 CPU）通常需要数十轮交互，无上下文管理会导致 Agent 在关键阶段「失忆」。压缩后的上下文保留电路拓扑概要，让 Agent 始终知道自己搭到了哪一步。

**工作量估计：** 2-3 天
- 后端：修改 `_build_autonomous_system_prompt`，添加压缩逻辑（1 天）
- JSON 序列化：将中间轮次转为结构化摘要（0.5 天）
- 测试 & 调参（0.5 天）

---

### 2.2 子代理系统（Subagent + 后台作业）← P0

**OpenCode 实现（tool/task.ts, agent/subagent-permissions.ts, background/job.ts）：**

```
task() 工具核心参数:
  - description: string          // 任务简述
  - prompt: string               // 完整指令
  - subagent_type: string        // 代理人类型
  - run_in_background: boolean   // 同步/异步
  - task_id: string              // 续传已有任务

权限继承规则:
  1. 继承父 agent 的 deny-edit 规则
  2. 继承父 session 的 deny 和 external_directory 规则
  3. 默认禁止 todowrite 和 task（除非显式允许）

后台作业生命周期:
  start → extend → wait → cancel → list → get
  状态: running / completed / error / cancelled
```

**TC 现状：** 通过 `task(subagent_type="explore")` 调用子代理，但无正式权限隔离，无作业管理（不能查询状态、取消、重试）。子代理可以执行电路修改命令。

**改进方案：**
- 创建 `spawn_agent` API：`POST /api/ai/spawn`，参数含 `agent_type`、`prompt`、`background`
- 子代理独立 `session_id`，继承父会话权限
- 限制子代理工具范围：explore 只读，test 只能 SET/SIM/SAMPLE，build 可写
- 后台作业管理：`GET /api/jobs/{id}`、`POST /api/jobs/{id}/cancel`
- 作业完成通过 SSE `__TC_JOB_STATUS__` 通知

**对电路搭建的价值：** 搭建中可并行发射子代理：一个探索元件库/模块，一个仿真验证已有电路，一个保持主设计流程进行。子代理的权限控制防止误操作。

**工作量估计：** 2-3 天
- 后端 API：spawn + jobs CRUD（1 天）
- 权限模型：角色→工具映射表（0.5 天）
- 前端 SSE 事件处理（0.5 天）

---

### 2.3 权限模型（Permission System）← P0

**OpenCode 实现（permission.ts, permission/schema.ts, agent/subagent-permissions.ts）：**

```
核心概念: 工具级权限 + 会话级权限继承

Permission.Request:
  - action: string         // 工具名
  - resources: string[]    // 目标资源
  - save?: string[]        // 记住此权限

Permission.Reply: "once" | "always" | "reject"

继承链:
  Agent Config → Session Defaults → Runtime Prompt → Tool Call
```

**TC 现状：** 完全无权限。AI agent 可执行 `CLEAR`（清空画布）、`DEL`（删除元件）、`DEFINE_MODULE`（修改模块）等全部命令。

**改进方案：**
- 为每个 Agent 角色定义权限规则：

| 角色 | 允许的命令 | 禁止的命令 |
|------|-----------|-----------|
| 观察者（Observer） | `SIM`, `SAMPLE` | 所有修改命令 |
| 建造者（Builder） | 所有建造命令 | — |
| 测试者（Tester） | `SET`, `TOGGLE`, `SIM`, `SAMPLE` | `CLEAR`, `DEL`, `DEFINE_MODULE` |
| 分析者（Analyst） | `SAMPLE`, `SIM` | 所有修改命令 |

- 权限存储在 `agent_config.json` 或 `TC_AGENTS.md`
- 会话级权限覆盖：子代理自动继承父代理的 deny 规则

**对电路搭建的价值：** 防止子代理误操作（探索中发出 CLEAR 命令清空搭了一半的电路）。测试 Agent 只能仿真不能修改，保证主电路不被破坏。

**工作量估计：** 1-2 天
- 权限定义 + 角色映射（0.5 天）
- `execute_command` 入口检查权限（0.5 天）
- 子代理权限继承逻辑（0.5 天）

---

### 2.4 指数退避重试 → P1

**OpenCode 实现（session/retry.ts）：**

```
RETRY_INITIAL_DELAY     = 2000       // 2s
RETRY_BACKOFF_FACTOR    = 2         // 2x
RETRY_MAX_DELAY         = 30_000    // 30s cap

retryable(error) → bool:
  - ContextOverflowError → false（换 compaction）
  - APIError & status >= 500 → true
  - TimeoutError → true
  - 4xx → false
```

**TC 现状：** `call_llm_stream` 无重试，`read_timeout` 后直接抛异常。长时间搭建电路时 API 不稳定会导致丢失进度。

**改进方案：**
- `call_llm_stream` 加入重试逻辑：
  - 5xx 错误：最多 3 次，2s→4s→8s
  - 超时：重试 1 次
  - 上下文溢出：切换 compaction 模式（不重试）
- `retryable()` 函数区分可重试/不可重试错误

**对电路搭建的价值：** 连续搭建 10+ 轮电路时 API 偶尔 5xx 或超时是必然的；重试保证搭建流程不中断。

**工作量估计：** < 1 天
- 修改 `call_llm_stream`，添加重试循环（0.5 天）

---

### 2.5 技能系统（Skill System）← P1

**OpenCode 实现（core/skill/）：**

```
技能来源:
  1. URL 远程技能库 → index.json → 按需拉取
  2. 本地 skills/ 目录 → 扫描 SKILL.md
  3. 已安装技能 → 状态恢复

格式标准化:
  ---
  name: string
  description: string
  triggers: string[]
  ---
  # 技能内容

发现过程: URL index.json → 并发下载 → 本地扫描 → 去重合并
```

**TC 现状：** `skills.md` 单文件，11 条技能，`_merge_skills()` 从 LLM 输出提取文本块并去重追加。无版本控制，格式松散。

**改进方案：**
- `skills/` 目录，每条技能一个独立 Markdown 文件
- 技能格式标准化：name / description / triggers / 正文
- `skills.md` → `skills/` 迁移，保持向后兼容（先读 skills/ 再 fallback 到 skills.md）
- 在 `_build_autonomous_system_prompt` 中按需注入技能（而非全部注入）

**对电路搭建的价值：** 技能系统让 Agent 可学习新的电路模式（如「识别 4-bit 加法器」「实现时钟分频」）。标准格式允许 Agent 将搭建经验写回技能库。

**工作量估计：** 3-4 天
- 技能发现扫描 + 格式解析（1 天）
- 技能注入逻辑改造（按需注入）（1 天）
- skills.md 向 skills/ 迁移（1 天）
- 技能提取优化（在 `_merge_skills` 基础上增强）（0.5 天）

---

### 2.6 指令系统（Instruction System）← P1

**OpenCode 实现（session/instruction.ts）：**

```
每次 LLM 调用前评估并刷新注入内容:
  - .claude/ 文件内容
  - 当前 Agent 配置
  - 用户偏好
  - 会话状态快照

特点: 动态、实时、可组合
```

**TC 现状：** `AI_INSTRUCTIONS.md` 静态文件，Agent 启动时读一次，运行期间不更新。电路状态变化（新元件、新模块）后 Agent 仍用旧指令。

**改进方案：**
- `AI_INSTRUCTIONS.md` 改为模板引擎，支持动态变量：
  - `{current_element_count}` — 当前元件数
  - `{current_module_list}` — 已定义模块列表
  - `{session_summary}` — 当前会话摘要
  - `{active_circuit_topology}` — 电路拓扑概要
- 每次 `_build_autonomous_system_prompt` 调用时重新渲染模板
- 加入「当前电路快照」块，让 Agent 知道当前电路状态

**对电路搭建的价值：** Agent 在搭建过程中实时感知电路状态（哪些模块已定义、当前元件数、拓扑结构），做出更合理的下一步决策。

**工作量估计：** 1-2 天
- 模板引擎 + 变量注入（0.5 天）
- 电路状态采集函数（当前元件/模块/拓扑统计）（0.5 天）
- 集成到 `_build_autonomous_system_prompt`（0.5 天）

---

### 2.7 Schema-first Agent 配置 ← P1

**OpenCode 实现（agent.ts）：**

```typescript
class Info {
  id: ID
  model?: ModelV2.Ref         // 绑定模型
  request: ProviderV2.Request  // 请求参数
  system?: string              // 系统提示词
  description?: string         // 用途描述
  mode: "subagent" | "primary" | "all"
  hidden: boolean
  color?: string               // UI 颜色标记
  steps?: number               // 最大步数
  permissions: Ruleset         // 权限集
}
```

**TC 现状：** `_AI_CONFIG_DEFAULTS` 字典（app.py）硬编码默认值，`ai_config.json` 可覆盖。不支持多 Agent 定义。

**改进方案：**
- 创建 `TC_AGENTS.md` 或 `agent_config.yaml` 定义多 Agent 角色：

```yaml
agents:
  builder:
    model: deepseek-chat
    temperature: 0.2
    mode: primary
    permissions: [ADD, WIRE, MOVE, DEL, COMMENT, DEFINE_MODULE]
    system_prompt: "你是电路搭建专家..."
  tester:
    model: deepseek-chat
    temperature: 0.1
    mode: subagent
    permissions: [SET, TOGGLE, SIM, SAMPLE]
    system_prompt: "你是电路测试专家..."
  analyst:
    model: deepseek-reasoner
    temperature: 0.3
    mode: subagent
    permissions: [SIM, SAMPLE]
    steps: 5
    system_prompt: "你是电路分析专家..."
```

- Agent 配置加载后以只读字典缓存，各 Agent 类型通过 `agent_type` 参数选择

**对电路搭建的价值：** 不同任务使用不同模型参数和提示词（测试用低温度保证确定性，分析用推理模型），提升各环节质量。

**工作量估计：** 1-2 天
- YAML/JSON 配置文件解析 + 校验（0.5 天）
- 多 Agent 选择 + API 适配（0.5 天）
- 向后兼容（默认 builder 角色）（0.5 天）

---

## 三、不采纳的 OpenCode 机制（不适用原因）

| 机制 | 不采纳原因 |
|------|-----------|
| 插件系统（Plugin Hook） | TC 场景不需要扩展钩子；Agent 直接执行命令即可 |
| 事件总线（Event Bus） | SSE 流直接推前端的模式足够简单，不需要事件抽象层 |
| MCP 集成 | TC 不需要外部工具集成，Agent 只操作电路 |
| SQLite 持久化 | JSON 文件够用（电路规模有限） |
| 结构化消息（Message Parts） | 当前 SSE 行协议 + `__TC_ROUND__` 标记简单够用 |
| 处理器系统（Processor） | 命令执行管道只有 3 步（解析→执行→反馈），不需要中间件 |
| 工具输出截断 | Agent 直接操作电路，工具输出小（命令确认），不需要截断 |

---

## 四、实施路线图

### 阶段 0：基础稳定性（< 1 天）
- [ ] 重试机制（2.4）：`call_llm_stream` 加指数退避
- [ ] 初步上下文管理（2.1）：简易裁剪（保留 N 轮，丢弃最旧）

### 阶段 1：核心能力（2-3 天）
- [ ] 权限模型（2.3）：角色定义 + 命令检查
- [ ] 子代理系统（2.2）：spawn API + 后台作业

### 阶段 2：增强能力（3-5 天）
- [ ] 完整上下文管理（2.1）：结构化 summary + 自动 compaction
- [ ] 指令系统（2.6）：模板 + 电路状态注入

### 阶段 3：生态扩展（3-5 天）
- [ ] 技能系统（2.5）：skills/ 目录 + 标准化格式
- [ ] Schema Agent 配置（2.7）：YAML 多角色定义

---

## 五、OpenCode 索引（供实现参考）

| 文件 | 路径 | 参考内容 |
|------|------|---------|
| retry.ts | opencode/src/session/retry.ts | 指数退避重试逻辑 |
| compaction.ts | opencode/src/session/compaction.ts | 上下文压缩策略 |
| overflow.ts | opencode/src/session/overflow.ts | 溢出检测阈值 |
| agent.ts | core/src/agent.ts + opencode/src/agent/agent.ts | Schema 定义、模式路由 |
| subagent-permissions.ts | opencode/src/agent/subagent-permissions.ts | 子代理权限继承 |
| permission.ts | core/src/permission.ts | 工具级权限模型 |
| task.ts | opencode/src/tool/task.ts | task() 工具实现 |
| job.ts | opencode/src/background/job.ts | 后台作业生命周期 |
| instruction.ts | opencode/src/session/instruction.ts | 运行时指令注入 |
| skill/discovery.ts | core/src/skill/discovery.ts | 技能发现 |
| skill.ts | core/src/skill.ts | 技能格式定义 |
| config/compaction.ts | core/src/config/compaction.ts | compaction 配置参数 |
