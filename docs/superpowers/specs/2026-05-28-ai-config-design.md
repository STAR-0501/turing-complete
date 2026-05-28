# AI 配置外部化设计文档

## 概述

移除 `app.py` 中硬编码的 API Key，改为从外部 JSON 配置文件读取。当配置文件缺失或无效时，在 Agent 侧边栏居中显示配置表单供用户填写，填写后持久化到文件。

## 动机

- **安全**：API Key 硬编码在源码中，提交到 Git 有泄露风险
- **可配置性**：用户可自由切换 API 地址、模型、Key，无需修改代码
- **开箱体验**：首次启动时引导用户配置，降低使用门槛

## 配置文件

### 位置

`ai_config.json`，放在项目根目录（与 `app.py` 同级）。

### 格式

```json
{
  "api_key": "sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "base_url": "https://api.deepseek.com",
  "model": "deepseek-v4-flash",
  "max_tokens": 4000,
  "connect_timeout": 10,
  "read_timeout": 180
}
```

### 加载逻辑

| 条件 | 行为 |
|------|------|
| 文件存在且包含有效 api_key | 正常启动，使用文件配置 |
| 文件不存在 / api_key 为空 | 标记为未配置，使用空默认值（所有 API 调用返回配置错误） |
| 文件存在但字段缺失 | 缺失字段回退到硬编码默认值 |

### .gitignore

`ai_config.json` 应加入 `.gitignore`，防止 API Key 意外提交。

## 后端变更

### 新增函数

| 函数 | 职责 |
|------|------|
| `load_ai_config()` | 启动时调用，从 `ai_config.json` 读取；文件不存在返回默认空配置 |
| `save_ai_config(data)` | 将配置写入 `ai_config.json`（原子写入） |
| `get_ai_config()` | 返回当前内存中的配置（含状态标记 `is_configured`） |

### 新增 API 路由

| 路由 | 方法 | 行为 |
|------|------|------|
| `/api/config` | GET | 返回当前配置（**不返回 api_key 明文**，仅返回 `has_key: bool`） |
| `/api/config` | POST | 接收 `{api_key, base_url, model, ...}`，保存到文件，更新内存配置 |

### 现有函数改造

`call_llm_once()` 和 `call_llm_streaming()`：移除对 `AI_CONFIG` 全局变量的引用，改为调用 `get_ai_config()`。

如果配置无效（api_key 为空），直接返回错误响应（后端不 panic，前端显示提示）。

### AI_CONFIG 常量

删除 `app.py` 第 24-28 行的 `AI_CONFIG` 字典。保留默认值作为 `load_ai_config()` 的后备。

## 前端变更

### 检测流程

`initChat()` 启动时：

1. `fetch('GET /api/config')`
2. 检查响应中的 `configured` 字段
3. **已配置** → 渲染正常聊天界面（现有逻辑）
4. **未配置** → 在 `#agent-messages` 中渲染配置表单

### 配置表单 UI

在 `#agent-messages` 区域居中渲染，取代普通消息：

```
┌─────────────────────────────┐
│        ◆ AI 配置             │
│                             │
│   API 地址                   │
│   ┌─────────────────────┐   │
│   │ https://api.deepseek│   │
│   └─────────────────────┘   │
│                             │
│   API Key                    │
│   ┌─────────────────────┐   │
│   │ ●●●●●●●●●●●●●●●●●  │   │
│   └─────────────────────┘   │
│                             │
│   模型 ID                    │
│   ┌─────────────────────┐   │
│   │ deepseek-v4-flash   │   │
│   └─────────────────────┘   │
│                             │
│   [▼ 高级设置]              │
│   ┌─────────────────────┐   │
│   │ max_tokens: 4000    │   │
│   │ 连接超时: 10s       │   │
│   │ 读取超时: 180s      │   │
│   └─────────────────────┘   │
│                             │
│   ┌─────────────────────┐   │
│   │      保存配置        │   │
│   └─────────────────────┘   │
└─────────────────────────────┘
```

### 交互细节

- API Key 输入框为 `type="password"`，带 👁 切换显示/隐藏
- 保存按钮：POST `/api/config` → 成功后重新加载侧边栏 → 显示聊天界面
- 保存失败（如网络错误）：显示错误提示，保持表单可见
- `[▼ 高级设置]` 为可折叠区域，默认折叠
- 所有输入框都有占位符提示默认值

### 样式

配置表单的样式新增在 `styles.css` 中，遵循现有侧边栏设计语言（深色主题）。

## .gitignore

将 `ai_config.json` 添加到 `.gitignore`。

## 安全考虑

- API Key 不在 GET 响应中返回明文，仅返回 `has_key: boolean`
- POST 请求保存后，配置在内存中保持明文供 API 调用使用
- 配置文件不在版本控制中

## 未涵盖的范围（本次不实现）

- 配置加密存储
- 多配置切换
- 配置验证（如测试 API 连接按钮）
