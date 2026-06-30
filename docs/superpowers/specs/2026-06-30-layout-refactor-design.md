# 设计文档：前端布局重构 + Agent 语义修复

- **日期**：2026-06-30
- **状态**：待实现
- **范围**：解决 AI 侧边栏 4 个问题——①折叠占位 ②元素粗糙 ③模型切换 ④`$方向` 引用语义 bug。重构为顶栏 + 可拖动 AI 右栏布局，并修复 agent 对 `$方向` 的理解。

---

## 1. 问题诊断

| 问题 | 根因 |
|---|---|
| ①折叠没完全收回 + 与 🤖 导航重复 | AI 栏用 CSS grid 第三列实现，折叠只改内容不释放列宽 → 永远占位；桌面 dock + 移动 🤖 导航逻辑重叠 |
| ②元素绘制粗糙 | toolbar/消息气泡/输入框是裸 div，缺乏层次、间距、状态反馈 |
| ③没有模型切换 | 模型配置锁在 SetupPanel，对话区无法切换 |
| ④agent 能力有问题 | `$agent` resolve 只返回方向名"AI Agent 🤖"，**不含节点列表/进度**；模型看不到 agent 方向有哪些节点，退回全局 get_progress 又跑偏查 DeepFM（见 `AI Agent学习方向.json` 对话记录） |

## 2. 设计决策（已与用户确认）

| 决策点 | 选择 |
|---|---|
| 布局 | **顶栏 + 主内容 + 右 AI 侧栏**，AI 展开挤压主内容（非遮盖） |
| AI 开合 | **顶栏右侧 ✦AI 按钮**控制开合 |
| 占比调节 | **可拖动分隔条**调节主内容与 AI 栏占比（clamp 280~600px），存 localStorage |
| 模型切换 | AI 工具条顶部**供应商下拉**（与对话区同宽） |
| agent 修复 | resolve `$` 展开节点 + 新增 get_direction 工具 + 引用注入聚焦 |

## 3. 整体布局

### 3.1 桌面端（≥820px）：顶栏 + 主内容 + 可拖动 AI 右栏

```
┌─顶栏──────────────────────────────────────────────────┐
│  🌳技能树  👤信息  📄模板  🍎果实      [✦AI] [⚙️]    │  sticky top
├────────────────────────────────────┬───────────────────┤
│                                    ║                   │
│  主内容(随顶栏切换)                  ║  AI 侧栏          │
│  · 技能树 DAG                       ║  (供应商▾+新对话)  │
│  · 个人信息等                       ║  (对话流)          │
│                                    ║  (输入框)          │
│        ←拖动这分隔条调占比→          ║                   │
│                                    ║                   │
└────────────────────────────────────┴───────────────────┘
```

**实现：**
- `.app` 从 `grid 256px 1fr clamp(...)` 改为 `grid 1fr`（单列），顶栏 `position:sticky; top:0; height:56px`
- 主内容区 + AI 栏用一个内层 grid：`grid-template-columns: 1fr var(--ai-width)`（AI 展开时）/ `1fr`（收起时）
- `--ai-width` CSS 变量，默认 `380px`，拖动时 JS 实时更新，存 `localStorage.ai_width`
- **分隔条**：`div.ai-resizer`，宽 6px，`cursor: col-resize`，监听 mousedown→mousemove 更新 `--ai-width`（clamp 280~600）
- **收起**：顶栏 ✦AI toggle `aiOpen` state，false 时 AI 栏 `display:none` + 内层 grid 变 `1fr`
- 删除旧左侧栏、旧 ai-dock/ai-page/FAB 全部相关代码

### 3.2 移动端（<820px）：顶栏 + AI 全屏覆盖

- 顶栏导航横向滚动
- AI 展开时**全屏覆盖**主内容（`position:fixed; inset:0`），不做挤压
- 顶栏 ✦AI 按钮 toggle 全屏 AI

## 4. AI 侧栏内部（同宽工具条 + 模型切换 + 样式重做）

### 4.1 工具条（与对话区同宽，整合所有操作）

```
┌─AI 侧栏─────────────────┐
│ 🤖 AI 助手          ✕   │  标题栏(收起✕)
├─────────────────────────┤
│ [供应商 ▾ DeepSeek  ] │  模型切换(同宽)
│ [▾ 当前会话] [+新对话] │  会话切换 + 新建
│ [🔍搜索] [⤓导出]      │  搜索/导出
├─────────────────────────┤
│  对话消息流(样式重做)    │
├─────────────────────────┤
│ [#节点 @资源 $方向]     │  mention 输入(同宽)
│                  [发送▸]│
└─────────────────────────┘
```

### 4.2 样式重做要点（解决"元素粗糙"）

- 用户气泡：右对齐，玉青底 `--moss`，圆角 12px，最大宽 80%
- 助手气泡：左对齐，无背景（融入），Markdown 渲染，玉青左边线
- 工具调用：玉青 chip + 图标，可折叠（默认折叠 tool_result）
- 思考过程：小字灰，默认折叠，点击展开
- 输入框：聚焦时玉青发光边框 `box-shadow: 0 0 0 2px var(--jade-soft)`
- 流式光标 ▌ 玉青闪烁
- 工具条按钮：统一样式（圆角 + hover 反馈 + 图标）

## 5. 模型切换

- 工具条顶部供应商下拉（同宽），列出 `GET /api/providers` 的供应商
- 切换时前端更新本地状态 + 调 `PUT /api/llm-config` 存新供应商
- 当前选中供应商高亮
- API key 沿用 llm_config.json（切换供应商时若该供应商未配 key，提示去设置页）

## 6. Agent 语义修复（`$方向` 真正可用）⭐

### 6.1 修复 1：resolve_refs 的 `$` 展开方向所有节点 + 进度

`chat_store.resolve_refs` 对 `$` 引用，现在只返回方向名，改为返回该方向所有节点 + 进度 + 下一步建议：

```
[方向] AI Agent 🤖 (LLM 基础 → RAG → Agent 框架...)
节点进度：
- Python (learning, 50%)
- Transformer (done, 100%)
- ReAct 范式 (locked, 0%)  ← 前置已满足，可学
- 主流 Agent 框架 (locked, 0%)
...
可推进的下一步：ReAct 范式、主流 Agent 框架（前置 transformer 已完成）
```

需要 resolve_refs 能访问该方向的节点 + progress。改造 main.py 的 `/api/chat/resolve` 端点：传入该方向的 trees + progress 计算结果。

### 6.2 修复 2：新增 get_direction 工具

Executor 工具集加 `get_direction(dir_id)`：
- 返回该方向所有节点 + 各自掌握度 + state
- 计算下一步建议（前置已满足的 locked 节点）
- 让 agent 能按方向查询，而非只能全局 get_progress

tool_runtime 加 `_get_direction` 实现 + 注册到 _REGISTRY；tools.py TOOLS_EXECUTOR 加 schema。

### 6.3 修复 3：引用注入聚焦

loop 的引用注入，把"用户引用了以下内容"改为更明确的聚焦指令：
```
用户引用了 $agent 方向，请聚焦该方向的节点和进度回答，不要扯到其他方向。
```

### 6.4 修复后效果

用户问 `$agent 下一步学什么`：
1. resolve_refs 展开 agent 方向所有节点（Transformer done、ReAct locked...）
2. 注入"聚焦 agent 方向"
3. 模型/或调 get_direction 工具，看到 ReAct/Agent框架等 locked 但前置已满足的节点
4. 给出 agent 方向的下一步建议（ReAct 范式、主流 Agent 框架），而非跑偏到 DeepFM

## 7. 文件改动清单

```
backend/
├── chat_store.py        【改】resolve_refs 的 $ 展开节点+进度(需接收 direction 数据)
├── main.py              【改】/api/chat/resolve 传入方向节点+progress
├── agent/tool_runtime.py【改】加 _get_direction 工具实现 + 注册
├── agent/tools.py       【改】TOOLS_EXECUTOR 加 get_direction schema
├── agent/loop.py        【改】引用注入聚焦指令
└── tests/
    ├── test_chat_store.py  【改】resolve $ 测试更新(展开节点)
    ├── test_tool_runtime.py【改】加 get_direction 测试
    └── test_loop.py         【改】引用注入聚焦测试

frontend/src/
├── App.tsx              【重写】删左侧栏→顶栏; 单列 grid; AI 右栏可拖动; 删 FAB/dock/page
├── AgentChat.tsx        【重写】工具条同宽+模型切换+样式重做; props 加 aiWidth/onResize
├── ChatToolbar.tsx      【重写】同宽工具条(供应商下拉/会话/搜索/导出/收起)
├── ChatMessage.tsx      【改】气泡样式重做(用户/助手卡片 + 工具折叠)
├── MentionInput.tsx     【改】聚焦发光边框
├── api.ts               【改】加 providers/saveLlmConfig 复用(已有)
├── types.ts             【改】加 Provider 类型(已有)
└── index.css            【重写相关区】顶栏 + 可拖动右栏 + 气泡 + 工具条 + resizer 样式
```

## 8. 范围与风险

### 8.1 范围（in scope）

- 顶栏 + 可拖动 AI 右栏布局（删除左侧栏/FAB/dock/page）
- AI 工具条同宽 + 模型供应商切换
- 消息气泡/工具条样式重做
- agent `$方向` 语义修复（resolve 展开节点 + get_direction 工具 + 注入聚焦）

### 8.2 风险

| 风险 | 缓解 |
|---|---|
| 拖动分隔条性能 | mousemove 节流（requestAnimationFrame）|
| 移动端拖动冲突 | <820px 禁用拖动，AI 改全屏覆盖 |
| resolve $ 展开数据多 | 只列节点名+state+_pct，不列 tasks 详情 |
| 供应商切换未配 key | 切换时检测，未配提示去设置页 |
| get_direction 计算下一步 | 复用 layout 的 depends_on + progress 的 node_status |
