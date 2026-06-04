## Agent 机制增强（2026-06-04 已全部实现）

1. ✅ **上下文压实** — turing_compactor.py：OverflowDetector + ContextCompactor 替代原有粗暴截断
2. ✅ **权限系统** — permissions.py：Permission 枚举 + TOOL_PERMISSIONS + PermissionChecker
3. ✅ **子代理系统** — subagent_manager.py：信号量并发控制、SPAWN/CHECK/WAIT 指令
4. ✅ **重试与退避** — retry.py：exponential_backoff 包装 LLM 调用，429/5xx 自动恢复
5. ✅ **技能系统** — turing_skills.py：结构化技能定义、SkillManager、skills/ 目录发现
6. ✅ **指令系统** — instructions.py：InstructionGroup + %%SCENARIO:xxx%% 情景标记
7. ✅ **配置治理** — agent_config.py + agent_config.yaml：AgentConfig 数据类 + YAML 加载

---

1. 修改函数内容
2. 增强AI能力
3. 界面导出/导入
4. 函数模块点击后没有浮在最上面
5. 注释功能
6. 添加AI功能：自动整理线路（一个按钮）  ； 手动ai注释
7. ai自动注释&ai自动排版加入默认指令

1. Agent 布局
2. 元件图案
3. 动画效果
4. Agent 记忆恢复
5. log 分对话保存
6. 左键拖拽 ctrl 框选
7. APIKEY 输入框
8. Arduino 代码转写
9. 代码重构
10. Function 的更名
11. 自动识别端口
12. 修复错乱提示
13. APIKEY 简单测试
14. [已修] 事件监听器未清理：chat.js mousemove/mouseup 改为拖拽时挂载/释放后移除；app.js contextmenu 改为命名函数

## AI 快捷按钮（已全部实现，按使用频率排序）
- AI测试：自动生成输入组合并仿真，验证电路输出
- AI查错：查找未连接端口、短路、开路、逻辑错误并给出修复建议
- AI注释：为所有元件添加说明注释
- AI整理：整理布局使电路清晰美观
- AI模块化：将选中元件封装为自定义模块
- AI连线：按逻辑关系自动连接元件
- AI分析：统计门数、层级深度、识别冗余逻辑
- AI优化：保持功能不变前提下化简逻辑减少门数
- AI解释：用自然语言描述电路功能