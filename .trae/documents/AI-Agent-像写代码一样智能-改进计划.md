## 总结

目标：把当前“电路搭建 AI”升级为更像写代码 Agent 的工作流（计划→执行→本地检查/自动测试→继续或停止），在能完成复杂电路的前提下减少空轮与 token 浪费。

本计划聚焦四类能力：

1. 确定性 I/O 控制与采样（SET / SIMULATE / SAMPLE）
2. 自动验证器（像跑单元测试一样自证正确）
3. 命令可靠性（强校验、可解释错误、少吞异常）
4. 记忆/分解（可复用的子目标与函数化策略，且不膨胀 token）

## 当前状态分析（基于仓库现状）

### 现有链路

* AI 主循环在 [app.py](file:///c:/Users/Administrator/Desktop/turing-complete/app.py) 的 `call_llm_stream()`：每轮构造 system prompt（含 compact\_state），调用一次 LLM，解析 `<commands>` 并执行，随后做检查并决定是否继续。

* 前端聊天在 [static/scripts/chat.js](file:///c:/Users/Administrator/Desktop/turing-complete/static/scripts/chat.js) 通过 `/api/chat` 流式消费，并在收到 `__TC_STATE_CHANGED__` 时刷新画布。

* 后端电路操作通过 `execute_circuit_command()`（同文件）分发到 `CircuitManager`（[ai\_commands.py](file:///c:/Users/Administrator/Desktop/turing-complete/ai_commands.py)）。

### 已具备能力（对“像 Agent 一样”有基础）

* 自治循环已有“停滞/循环/重复错误”停止条件，能减少空转调用（在 `call_llm_stream` 内实现）。

* 后端已支持 FUNCTION 递归仿真、多输出按端口取值；前端也已修复多输出取值与迭代收敛问题（`static/scripts/circuit.js`）。

* alias 已持久化：`ADD ... [alias]` 会写入 `element.alias`，并在后续轮次可用 alias 引用。

### 仍然阻碍复杂任务的关键缺口

1. **输入控制不确定**：只有 TOGGLE，无法可靠设置为 0/1；复杂验证容易“翻错一次就跑偏”。
2. **缺少标准化“仿真/采样”接口**：AI 只能读 compact\_state 的 state，缺少清晰的“跑测试→断言”的闭环指令。
3. **命令执行吞异常/缺少诊断**：解析/执行阶段对异常常 `except: continue`，导致“看似执行了但没生效”，模型难以自我修复。
4. **缺少轻量的结构化验证回路**：目前主要靠模型自评 done；复杂电路需要像写代码那样有“测试报告”驱动下一轮。

## 拟议改动（按优先级）

### P0：增加确定性 I/O 控制与采样（SET / SIMULATE / SAMPLE）

#### 目标与收益

* 让 AI 能用确定性方式控制输入并采样输出，形成“搭建→仿真→验证”闭环。

* 为后续自动验证器提供稳定底座。

#### 后端改动

* 文件：[ai\_commands.py](file:///c:/Users/Administrator/Desktop/turing-complete/ai_commands.py)

  * 增加 `CircuitManager.set_input(element_id, value: bool)`：直接写入 INPUT 的 `state`，并触发 `simulate()`。

  * 增加 `CircuitManager.sample_outputs(output_ids: list[str]|None)`：

    * 默认采样全部 OUTPUT 元件的 `state`

    * 若给 ids，则按 ids 返回

    * 返回建议为 `{ "outputs": [{"id": "...", "alias": "...", "state": true}, ...] }`

* 文件：[app.py](file:///c:/Users/Administrator/Desktop/turing-complete/app.py)

  * `execute_circuit_command()` 新增分支：

    * `set_input`

    * `simulate`（显式调用 `circuit_manager.simulate()`）

    * `sample_outputs`

  * `_parse_commands_payload()` 扩展 DSL：

    * `SET <id_or_alias> <0|1>`

    * `SIM`（或 `SIMULATE`）

    * `SAMPLE [id_or_alias ...]`（可选）

  * `_build_autonomous_system_prompt()` 追加说明：复杂电路应使用 SET+SAMPLE 做验证，并以验证结果决定 done。

#### 验证方式

* 用 `python -c` 方式做一次端到端验证（不新增仓库文件）：

  * 创建 INPUT/OUTPUT，SET 输入，SIM，SAMPLE 输出，断言输出 state 与预期一致。

### P1：自动验证器（像跑单元测试一样）

#### 目标与收益

* 让 AI 对复杂电路能“自己写测试、自己跑测试、拿测试结果决定继续或 done”，减少反复自问自答和空轮 API 调用。

#### 方案（最小可落地）

在 LLM 输出结构中新增可选 `<verify>` 块（JSON），服务端解析并执行验证：

* LLM 输出示例（只要结构，不强制每轮都要）：

  * `<verify>{"inputs":[{"id":"A","value":0},{"id":"B","value":1}],"expect":[{"id":"SUM","value":1},{"id":"CARRY","value":0}]}</verify>`

  * 支持多 case：`{"cases":[...]}`

* 服务端执行流程（在 `call_llm_stream()` 每轮“执行 commands”后）：

  1. 解析 `<verify>`（如果存在）
  2. 对每个 case：

     * 对输入执行 `set_input`（允许 alias）

     * `simulate`

     * `sample_outputs`（采样期望的 OUTPUT 或全部 OUTPUT）

     * 生成 pass/fail 报告
  3. 将报告作为“系统检查反馈”追加进下一轮 `request_messages`
  4. 若所有 case 通过且本轮无新命令需要执行，则允许自动 done（减少下一轮调用）

#### 边界与安全

* `<verify>` 只允许读写 INPUT state 与读取 OUTPUT state，不允许增删改元件；避免验证逻辑改变电路结构。

* 限制 case 数量（如 16）避免 token/时间爆炸；超限时只跑前 N 个并明确提示。

#### 验证方式

* 构造一个半加器/全加器的小例子：

  * AI 建电路 + 输出 `<verify>` truth table 的若干行

  * 观察系统返回的验证报告，并确认 AI 能据此收敛到 done=true。

### P2：命令可靠性（强校验、少吞异常、可解释）

#### 目标与收益

* 让 AI 遇到错误能拿到“可修复”的具体原因，而不是无声失败。

* 显著减少空轮与重复错误。

#### 改动点

* 文件：[app.py](file:///c:/Users/Administrator/Desktop/turing-complete/app.py)

  * `_execute_commands_with_alias()`：将当前“吞异常 continue”改为“收集错误列表”并在本轮检查输出里显示（同时也作为下一轮系统反馈）。

  * 增加本地预校验：

    * id/alias 是否存在

    * 端口索引是否越界（结合当前 state 中 inputs/outputs 长度）

    * 目标输入端口是否已有连接（可选策略：禁止多重驱动，或允许但提示）

  * 将错误以结构化摘要返回给模型：`[执行错误] command=..., reason=..., hint=...`

#### 验证方式

* 人为构造一条错误命令（不存在的 alias、越界端口），确认系统能输出明确错误原因，并且 AI 下一轮能修复为正确命令。

### P3：更强记忆/分解（不膨胀 token）

#### 目标与收益

* 复杂电路往往需要多轮：拆分子目标、函数化复用、验证与布局整理。希望 AI 像写代码 agent 一样维护“当前进度/已验证结论”，但又不把上下文越堆越大。

#### 最小实现

* 文件：[app.py](file:///c:/Users/Administrator/Desktop/turing-complete/app.py)

  * 在每轮系统反馈中追加极小的“结构化摘要”而不是全量 state\_fingerprint：

    * 当前已知 alias 的 INPUT/OUTPUT 列表（只列 id+alias+state）

    * 最近一次验证报告摘要（通过/失败项）

  * 对 `compact_state_json` 保持简洁（已经使用 separators 压缩），避免重复附带大段无用文本。

#### 验证方式

* 对一个需要 10+ 个输入输出的复杂函数（如 4-bit ripple-carry adder）观察 token/轮次显著下降，且 AI 能持续引用关键 alias 不迷路。

## 假设与决策（已从对话锁定）

* 交付物：你要“改进清单 + 可执行计划”，确认后再进入实现阶段。

* 优先级：SET/SIM/SAMPLE、自动验证器、命令可靠性、记忆/分解都要做；同时希望减少空轮、在效果最大化前提下节省 token。

* 主要验收：能完成复杂电路（例如加法器/比较器等）并能稳定迭代到 done。

## 实施顺序（建议）

1. P0：SET/SIM/SAMPLE（打基础，后续都依赖）
2. P2：命令可靠性（减少“执行了但没生效”）
3. P1：自动验证器（将“done”变成可证据驱动）
4. P3：记忆/分解摘要优化（进一步降轮次与 token）

## 验收清单（最终）

* AI 能用 SET 将输入置 0/1，并通过 SAMPLE 读到输出，形成闭环。

* 对多输入多输出、嵌套 FUNCTION 的复杂电路，验证器能稳定跑 case 并给出 pass/fail 报告。

* 错误命令不再无声失败；系统能反馈可修复原因。

* 在同等目标下，平均轮次与无效调用减少（至少能观察到“不再空转到 max\_rounds”）。

