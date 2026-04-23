# ai_commands.py 重构计划

## 总结
针对 AI 代码审查报告中指出的 `ai_commands.py` 结构臃肿、嵌套过深、缺乏注释和日志等问题进行重构。本次重构旨在提升代码的可维护性、可读性和单一职责（SRP），同时保证后端电路仿真和指令执行的核心逻辑不变。

## 现状分析
根据探测和审查报告，`ai_commands.py` 存在以下主要问题：
1. **仿真引擎嵌套过深**：`_simulate_elements_until_stable` 包含 6 层嵌套，且混杂了收敛判断与针对 `AND/OR/NOT` 等各个元件的硬编码计算逻辑。
2. **`add_element` 函数过长**：接近 100 行，包含大量 `if-elif-else` 链用于生成不同元件的宽高、端口坐标。
3. **`_normalize_wire` 职责不单一**：同时处理两种不同版本的连线格式（`start/end` 和 `from/to`）。
4. **参数过多**：`_calculate_function_element` 等函数接收多达 6 个参数，数据传递不清晰。
5. **缺少文档与日志**：整个文件基本没有函数注释，异常捕获后没有使用标准日志记录上下文。

## 提议的变更

### 1. 提取仿真核心逻辑 (Simulation Engine Extraction)
- 将 `_simulate_elements_until_stable` 中的每个元件状态计算逻辑提取到独立方法 `_calculate_single_element(el, context)`。
- 为不同类型的元件（AND, OR, NOT, OUTPUT）建立单独的计算方法，如 `_calc_and_gate`，用映射表（策略模式）取代巨型 `if-elif`。

### 2. 引入 `SimulationContext` Dataclass
- 新增 `@dataclass class SimulationContext:`，将 `elements`, `wires`, `function_cache`, `depth` 封装为一个对象，大幅减少 `_calculate_function_element` 和各计算函数的参数传递数量。

### 3. 拆分元件生成逻辑 (`add_element` Refactoring)
- 新增 `_get_element_template(element_type)` 方法，返回一个包含元件宽高和端口定义的字典。
- 将原本在 `add_element` 中的大段 `if-elif` 移至该方法，使得 `add_element` 自身仅关注业务流：获取模板 -> 设置位置和别名 -> 存入电路。

### 4. 拆分连线规范化 (`_normalize_wire` Refactoring)
- 提取 `_normalize_standard_wire(wire, elements)` 和 `_normalize_legacy_wire(wire, elements)`，分别处理当前格式和兼容旧格式。

### 5. 添加文档注释与标准日志 (Docstrings & Logging)
- 在文件顶部引入 `import logging` 并配置一个内部 logger。
- 替换现有抛出异常或静默失败的地方，加入 `logger.error` 记录上下文。
- 为模块和类（特别是公共 API 如 `get_state`, `add_element`, `simulate` 等）添加清晰的中文/英文 Docstring。

## 假设与决策
- **不改变公共接口签名**：为了避免级联破坏 `app.py` 中的调用，`CircuitManager` 的对外接口定义（如 `add_element(self, element_type, x, y, alias=None)`）保持不变。
- **等价性**：递归函数的处理和多路输出的取值逻辑必须保持现有的等效，确保复杂电路仿真不崩溃。

## 验证步骤
1. 完成重构后，通过执行 `python -c "import ai_commands"` 确保无语法和依赖错误。
2. 启动应用程序，验证拖拽和连线的基本操作是否存盘成功。
3. 观察应用日志，验证错误发生时是否正确记录。
4. 调用复杂的 AI 功能生成电路（涉及嵌套的 FUNCTION 元件），检查仿真是否正确计算出状态并收敛。