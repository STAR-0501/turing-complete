# AI 电路搭建行为改进计划

## 总结
目标：解决 AI 在复杂电路搭建中"一次输出上百命令→坐标算错→部分失败→整轮废掉"的问题。改进思路是**限步数、强验证、减废话**，让 AI 像靠谱的工程师一样一小步一小步搭，每步验证通过再继续。

## 现状问题（实测数据支撑）
- 用户发"你好"要跑 2 轮自治循环（已通过 `_quick_classify` 解决）
- 搭乘法器时一轮输出 108 条命令，坐标算错（P0~P5 与 A0~A2/B0~B2 的 y 完全重合）导致 4 个 ADD 失败，后续 30+ WIRE 全报 "Invalid element IDs"
- `<plan>` 经常写 500+ 字的数学推导 + 坐标穷举 + 多种方案的优劣势讨论，消耗大量 token 但不产生实际价值
- `system prompt` 虽然有"每完成一个子目标就验证"的规则，但模型完全忽视

## 改动方案

### 1. 单轮命令数上限：30 条/轮
**文件**: [app.py:call_llm_stream](file:///c:/Users/Administrator/Desktop/turing-complete/app.py#L1091)
- 在 system prompt 中硬性增加一条：`每轮最多输出 30 条命令。如果目标需要超过 30 条命令，分多轮完成，每轮完成后先验证再继续。`
- 同时在 `_feed_stream_text` 执行解析后，如果 `executed_command_count` 超过 30，自动截断当前 `</commands>` 块之后的命令不执行，并在系统反馈中提示 LLM"本轮命令数已达上限(N=30)，请在下轮继续"。

### 2. 强制分步验证：函数定义后自动跑测试再 CLEAR
**文件**: [app.py:_build_autonomous_system_prompt](file:///c:/Users/Administrator/Desktop/turing-complete/app.py#L904-L967)
- 在规则中增加一条硬性约束：`DEFINE_FUNC 后，必须用 SET + SAMPLE 验证函数功能正确，才能 CLEAR。未验证就 CLEAR 视为错误。`
- 建议的步骤模板：`搭建子电路 → DEFINE_FUNC → SET+SAMPLE 验证 → 通过后 CLEAR → 用 ADD <函数名> 复用`

### 3. 自动坐标偏移替代手动算坐标
**文件**: [app.py:_build_autonomous_system_prompt](file:///c:/Users/Administrator/Desktop/turing-complete/app.py#L904-L967)
- 增加新规则：`不要手动为每个元件计算精确坐标。相反，使用基准坐标 + 相对偏移。例如：输入用 x=80,y=60,120,180...；门电路用 x=240, y 与对应输入对齐；输出用 x=560。所有同类型元件的 y 间距固定为 80。`
- 删除原来过于复杂的"推荐布局"段落（x=80/240/400/560/720 分层 + y=60/120/180），改为更简洁的上规则，减少模型认知负担。

### 4. `<plan>` 长度约束
**文件**: [app.py:_build_autonomous_system_prompt](file:///c:/Users/Administrator/Desktop/turing-complete/app.py#L904-L967)
- 在 `<plan>` 说明中增加：`<plan> 不超过 80 字，只写"做什么 + 坐标策略"。不需要解释逻辑门原理、不需要推导真值表、不需要讨论可不用的方案。`
- 在 `_execute_commands_with_alias` 执行后也可以考虑在系统反馈中隐式缩短 `compact_state` 的重复发送。

### 5. 后端增加坐标重叠的主动拦截（加分项）
**文件**: [app.py:execute_circuit_command](file:///c:/Users/Administrator/Desktop/turing-complete/app.py#L121-L144) 或 [ai_commands.py:add_element](file:///c:/Users/Administrator/Desktop/turing-complete/ai_commands.py#L241-L257)
- 在 `add_element` 中加入"检查新元件是否与已有元件重叠"的预检查，如果重叠则自动修正坐标（沿着 y 方向递推 80 像素）并返回实际坐标给 AI，让 AI 知道被调整了，逐步学会规划布局。
- 注意：为了不破坏原有行为，这应该是"自动修正"而非"拒绝"，修正值在返回结果里标明。

## 假设与决策
- 命令数上限 30 是根据"一次搭建半加器（约 10 条）到全加器（约 20 条）"的典型规模估算的，过大过小需实测调整。
- 坐标自动修正只做"沿 y 偏移"的简单策略，不做复杂的螺旋搜索（JS 前端已有 `findNonOverlappingPosition`）。
- `<plan>` 的 80 字限制可能在复杂任务下过于严格，可考虑放宽到 120 字但强调"只写决策"。

## 验收标准
1. AI 不再一轮输出 50+ 条命令（单轮上限 30）
2. 搭建半加器/全加器时，每搭完一个子电路就做 SET+SAMPLE 验证，再 CLEAR 复用
3. `<plan>` 显著缩短（不再出现长篇数学推导）
4. 坐标重叠导致的 ADD 失败显著减少（自动修正兜底）
