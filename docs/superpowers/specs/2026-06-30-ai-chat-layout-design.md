# 设计文档：AI 对话区改造（独立常驻 + 多会话 + 流式 + Markdown）

- **日期**：2026-06-30
- **状态**：待实现
- **范围**：把 AI 从右下角临时悬浮 FAB 改造为系统一等公民——响应式独立对话区（桌面三栏常驻 / 移动独立页）、多会话管理（`/new` + 历史切换）、跨会话搜索与导出、全链路真流式 token 渲染、Markdown 渲染。

---

## 1. 背景与动机

### 1.1 现状

`AgentChat.tsx` 当前是右下角悬浮 FAB 弹出的小窗：
- 对话记录用 `useState` 持有，关掉 FAB 或刷新即丢失。
- 单一会话，无法开新对话或回看历史。
- 挤在屏幕角落，AI 是系统里唯一的「浮窗孤岛」，与其他侧栏 panel 范式不一致。
- `final_answer` 是一次性整段纯文本，Agent 返回的 markdown 原样显示，无流式逐字效果。

### 1.2 目标

五个诉求：
1. **AI 独立成系统一等公民**：右侧永远常驻的独立交互部分（桌面三栏），与侧栏各板块平级。
2. **对话持久化**：关窗/刷新不丢，跨设备同步。
3. **多会话**：`/new` 命令开新会话 + 顶部下拉切换历史会话。
4. **跨会话搜索 + 导出**：搜全部历史会话，命中可跳转；支持导出。
5. **全链路真流式**：从 LLM 流式输出 → SSE → 前端逐字渲染。
6. **Markdown 渲染**：标题/列表/代码块/引用/表格正确呈现，符合玉青宝石工坊美学。

### 1.3 设计决策（已与用户确认）

| 决策点 | 选择 | 理由 |
|---|---|---|
| 布局形态 | 响应式：桌面三栏（侧栏+主区+常驻 AI 窗口）；移动端 AI 作侧栏独立项切全屏页 | 桌面边用边问、移动不挤压 |
| 对话持久化 | 前后端双写：后端权威 + 前端 localStorage 缓存 | 跨设备同步 + 首屏快 |
| 多会话组织 | 单一活跃会话 + `/new` 开新会话 + 顶部下拉切历史 | 轻量、符合 chat 习惯 |
| 搜索范围 | 跨所有会话 | 配合多会话最实用 |
| 导出 | 支持导出（Markdown 文件） | 配合搜索 |
| 流式 | 全链路真流式（LLM 流式 → SSE delta → 逐字渲染） | 体验最好、面试讲完整链路 |
| Markdown | marked + DOMPurify + highlight.js | 业界标准、安全、生态好 |

## 2. 总体布局（核心）

### 2.1 桌面端（≥820px）：三栏，AI 永远常驻

```
┌─侧栏─┬────主区(随侧栏导航变)────┬──AI常驻窗口──────┐
│ 🌳   │                          │ ▾ 主题·14:30  ◂ │ ← 会话下拉+折叠
│ 👤   │  当前板块内容:            │ ─────────────── │
│ 📄   │  · #tree → 知识图谱 DAG   │ 🔍 搜索  ⤓导出 │ ← 工具条
│ 🍎   │  · #profile → 个人信息    │ ─────────────── │
│      │  · #templates → 简历模板  │ [用户]          │
│      │  · #fruit → 果实展示      │ 我学到哪了      │
│      │                          │                 │
│      │  ← 切换侧栏,主区变,       │ [助手] 💭       │
│ ⚙️   │    但 AI 右栏不动!        │ 🔧get_progress  │
│ 45%  │                          │ 你整·体·45%… ▌ │ ← 流式逐字
└──────┴──────────────────────────┤ ─────────────── │
                                  │ [输入框][/new]▸ │
                                  └─────────────────┘
```

**关键**：`<App>` 的 grid 从 `256px 1fr` 变成 `256px 1fr clamp(320px, 28vw, 440px)`。AI 栏是 App 的**直接子元素**，不嵌在任何路由 panel 内——切换侧栏板块时它纹丝不动。

- **可折叠**：顶部 ◂ 收成窄边（只留 ✦），点开恢复，状态记 localStorage。
- **AI 栏内部三段**：顶部工具条（会话下拉 + 搜索 + 导出 + 折叠）/ 中间消息流 / 底部输入框。

### 2.2 移动端（<820px）：AI 作侧栏独立项

```
┌─侧栏(横向)──────────────────────────────────┐
│ 🌳技能树  👤信息  📄模板  🍎果实  🤖AI  ⚙️   │  ← 🤖 切 #chat
└──────────────────────────────────────────────┘
点 🤖 → 全屏 chat 页面(含工具条/消息流/输入框)
```

### 2.3 一个组件两种容器

`<AgentChat>` 组件逻辑不变，靠 CSS 控制父容器：桌面挂在 App 右栏（class `ai-dock`），移动挂在 `#chat` 路由（class `ai-page` 全屏）。

## 3. 路由与导航

- **桌面侧栏**：保持 4 项（🌳👤📄🍎）+ 设置。**不加 🤖**——AI 栏永远常驻。
- **移动端横向侧栏**：多一个 🤖AI 项，切 `#chat` 全屏页。
- **删除旧 FAB**：移除右下角悬浮 ✦ 按钮及相关逻辑。
- 路由：`#tree`(默认) / `#profile` / `#templates` / `#fruit` / `#chat`(移动端) / `#setup` / `#settings`。

## 4. 多会话管理

### 4.1 数据模型

对话从单一对象升级为「会话列表」：

```json
// data/users/<uid>/chat_history.json
{
  "sessions": [
    {
      "id": "s_1719700000",
      "title": "DeepFM 学习",          // 首条用户消息截断生成
      "created_at": "2026-06-30T14:00:00",
      "updated_at": "2026-06-30T14:30:00",
      "messages": [
        {"role":"user","content":"…","ts":"…"},
        {"role":"assistant","content":"…","events":[…],"ts":"…"}
      ]
    },
    ...
  ],
  "current_session_id": "s_1719700000",
  "updated_at": "2026-06-30T14:30:00"
}
```

### 4.2 会话操作

| 操作 | 触发 | 行为 |
|---|---|---|
| 新建会话 | 输入 `/new` 或点「+ 新会话」 | 当前会话归档，创建空会话设为 current |
| 切换会话 | 顶部下拉点历史项 | current_session_id 切换，加载该会话消息 |
| 标题生成 | 会话首条用户消息后 | **LLM 生成标题**（异步：先临时用首句，LLM 返回后替换）；后端 `/api/chat/title` |
| 删除会话 | 下拉项旁的 ✕ | **二次确认弹窗**（"删除此会话？不可恢复"）后从 sessions 移除 |

### 4.3 命令系统（`/new` 起步）

输入框识别 `/` 开头的命令：
- `/new` → 新建会话
- （预留扩展：`/clear`、`/export` 等未来可加）

命令不发给 LLM，前端本地处理。

## 5. 跨会话搜索与导出

### 5.1 搜索

- **入口**：AI 栏工具条 🔍 按钮 → 展开搜索框。
- **范围**：跨所有历史会话的消息（user + assistant content）。
- **实现**：后端 `GET /api/chat/search?q=xxx` 遍历 sessions 做子串匹配（数据量小，无需全文索引），返回 `[{session_id, session_title, message_index, snippet, role}]`。
- **结果展示**：下拉列表，每条显示会话标题 + 命中片段（高亮）+ 来源。点击 → 切换到该会话并滚动到该消息。

### 5.2 导出

- **入口**：工具条 ⤓ 按钮。
- **范围**：导出当前会话（默认）或全部会话（可选）。
- **格式**：**JSON 文件**（`会话标题.json`），结构化保存完整 sessions 数据（含 messages/events/ts/引用解析），便于后续再导入或分析。
- **实现**：后端 `GET /api/chat/export?session_id=xxx&all=false` 返回 `application/json`，前端触发下载（Blob + a.download）。

## 6. 符号引用（#节点 / @资源 / $方向）

### 6.1 符号语义

在对话输入中用符号引用系统内的对象，AI 回答时能看到被引用对象的完整内容（增强上下文）：

| 符号 | 引用对象 | 示例 | 展开内容 |
|---|---|---|---|
| `#` | **技能树节点** | `#deepfm` | 节点详情：任务/验收/依赖/掌握度 |
| `@` | **资源**（论文/源码文件） | `@dssm论文`、`@deepfm.py` | 论文 abstract / 源码片段 |
| `$` | **方向/分支** | `$推荐` | 该方向所有节点概览 |

### 6.2 双触发机制（两者结合）

**A. 输入时 mention 补全**（前端）：
- 输入框检测到 `#` / `@` / `$` 后触发补全弹层。
- `#` → 拉技能树节点列表（`GET /api/graph` 的 nodes）模糊匹配。
- `@` → 拉资源列表（节点 resource 字段里的论文链接 + 源码文件路径）。
- `$` → 拉方向列表（dir_order）。
- 选中后插入规范标记（如 `#deepfm`），弹层关闭。
- Esc / 空格 / 选完关闭弹层。

**B. AI 自动解析**（后端）：
- 即使没走补全（用户手打 `#DeepFM`），后端在把消息送进 Agent loop 前，**预处理扫描**消息里的 `#xxx` / `@xxx` / `$xxx`。
- 命中的对象内容**作为额外上下文注入** Executor 的 system prompt（"用户引用了以下内容：…"）。
- 这样 AI 无论用户是否用补全，都能"看到"被引用对象。

### 6.3 引用解析端点

- `GET /api/chat/resolve?refs=#deepfm,@dssm,$推荐` → 后端解析符号，返回各对象的展开内容 `[{type, id, content}]`。
- 前端补全用它的子集（如只列节点名）；后端 Agent loop 内部用它的完整版（注入 prompt）。

### 6.4 引用渲染

- 消息中的 `#deepfm` 渲染成**玉青色可点击 chip**（点击跳到该节点/资源/方向）。
- 不破坏 Markdown 解析（chip 用特殊 span，marked 转义后再替换）。

### 6.5 面试讲法

mention 补全（输入体验）+ 后端预处理注入（保证 AI 一定能看到引用内容，双保险）；符号语义对应系统的三类对象（节点/资源/方向）；引用既增强 AI 上下文又能在 UI 可视化跳转。

## 7. 全链路真流式

### 7.1 流式链路

```
LLM 流式 API (stream:true)
   │  逐 token delta
   ▼
agent/protocol.py chat_stream()  ← 已存在(T9 实现),逐 chunk yield {type:delta}
   │
   ▼
agent/loop.py run_agent()  ← 改造:Executor 的最终回答用流式产出
   │  yield SSE 事件
   ▼
/api/agent/chat (SSE)  ← 已存在
   │  data: {type: "delta", content: "你"}
   │  data: {type: "delta", content: "整体"}
   ▼
AgentChat 前端  ← 改造:delta 事件逐字追加到当前 assistant 消息
   │  实时渲染 + Markdown 流式解析
```

### 7.2 loop 改造点

当前 `run_agent` 在 Executor 拿到 `Final Answer` 后一次性 `yield {"type":"final_answer","content":...}`。改造为：
- 检测到 Final Answer 时，**用 `chat_stream` 重新流式生成**该回答（或让 Executor 的 LLM 调用本身就是流式）。
- 逐 token `yield {"type":"delta","content":token}`，最后 `yield {"type":"final_done"}`。
- 工具调用阶段（Thought/Action/Observation）保持非流式（工具调用结构需完整解析，不适合流式）。

**简化策略（推荐）**：Executor 的 ReAct 循环非流式跑完工具调用；当判定要给最终回答时，发起一次**流式 LLM 调用**专门产出最终回答，逐字 yield。这样工具调用的可靠性 + 最终回答的流式体验兼得。

### 7.3 前端流式渲染

- 收到 `delta` 事件 → 追加到当前 assistant 消息的 content。
- **流式过程中用纯文本快速渲染**（避免每个 token 都跑 marked 解析卡顿）。
- 收到 `final_done` → 跑一次完整 Markdown 解析渲染最终效果。
- 流式时显示光标 `▌`。

## 8. 对话记忆（前后端双写）

### 8.1 数据流

```
用户发消息 → AgentChat 乐观更新 UI → POST /api/agent/chat (SSE)
                │                              │
                │   ◀── SSE 事件流(delta/tool/final_done)
                ▼                              ▼
            前端 messages 累加         后端 Agent loop
                │
                ▼
        final_done 后 → 更新 localStorage + POST /api/chat/sync (双写)
```

### 8.2 端点（含多会话/搜索/导出/引用）

| 端点 | 方法 | 作用 |
|---|---|---|
| `/api/chat/history` | GET | 返回 `{sessions, current_session_id}`（首屏加载） |
| `/api/chat/sync` | POST | body `{sessions, current_session_id}`，覆盖存储 |
| `/api/chat/title` | POST | body `{message}`，LLM 生成会话标题，返回 `{title}` |
| `/api/chat/search?q=` | GET | 跨会话搜索，返回命中列表 |
| `/api/chat/export?session_id=&all=` | GET | 导出 JSON，返回 `application/json` |
| `/api/chat/resolve?refs=` | GET | 解析 `#node,@res,$dir` 符号，返回各对象展开内容 |
| `/api/chat/suggest?type=&q=` | GET | mention 补全：按类型(node/resource/dir)+前缀模糊匹配 |
| `/api/agent/chat` | POST(SSE) | 已有；消息预处理注入引用上下文 + 流式 delta |

### 8.3 前端缓存

- 首屏：读 localStorage `chat_<uid>` 秒开 → `GET /api/chat/history` 校正（后端权威）。
- 每轮 final_done：更新 localStorage + `POST /api/chat/sync`。
- 用户切换：清缓存 key 重拉。

## 9. Markdown 渲染

### 9.1 组件

新建 `Markdown.tsx`：`marked.parse` → `DOMPurify.sanitize` → `dangerouslySetInnerHTML`；代码块 highlight.js 高亮（只引 common 语言包控体积）。

### 9.2 安全

marked 默认不转义 HTML，**必须 DOMPurify.sanitize** 防 XSS。

### 9.3 样式（玉青宝石工坊）

| 元素 | 样式 |
|---|---|
| `h1/h2/h3` | Fraunces 衬线，玉青色，左侧玉青竖线 |
| 行内 `code` | JetBrains Mono，`--moss-2` 底，玉青文字 |
| ` ``` 代码块 ``` ` | 深墨底 + 玉青边框 + 左侧色带 + highlight.js |
| `blockquote` | 左玉青竖线 + `--fg-dim` 斜体 |
| `ul/li` | 玉青圆点 |
| `table` | 玉青表头底，玉青边框 |
| `strong` | `--gold` 金芽色 |

## 10. 文件改动清单

```
frontend/src/
├── AgentChat.tsx      【重写】悬浮窗 → 响应式对话区(常驻 dock / 全屏 page)
│                          + 会话下拉 + 搜索框 + 导出按钮 + /new 命令 + 流式渲染
├── ChatMessage.tsx    【改】流式光标 + final_done 后 Markdown 渲染 + 引用 chip 渲染
├── Markdown.tsx       【新】marked + DOMPurify + highlight.js
├── ChatToolbar.tsx    【新】AI 栏顶部工具条(会话下拉/搜索/导出/折叠)
├── MentionInput.tsx   【新】输入框 + #/@/$ mention 补全弹层
├── api.ts             【改】新增 chat 全套端点(history/sync/title/search/export/resolve/suggest)
├── types.ts           【改】Session/ChatHistory/Ref 类型; ChatMessage 加 ts
├── App.tsx            【改】三栏 grid; 侧栏加 🤖(移动); AI 栏常驻; 删 FAB; 加 #chat
└── index.css          【改】三栏响应式 + .md 样式 + AI 栏 + 工具条 + mention 弹层样式

backend/
├── main.py            【改】chat 端点(history/sync/title/search/export/resolve/suggest)
└── agent/loop.py      【改】消息预处理注入引用上下文 + Executor 最终回答改流式 yield delta

依赖: npm i marked dompurify highlight.js (+ @types)
```

## 11. 范围与风险

### 11.1 范围（in scope）

- 三栏响应式布局 + 删 FAB
- 多会话（`/new` + 下拉切换 + LLM 标题 + 删除二次确认）
- 跨会话搜索 + 导出（JSON）
- 符号引用（#节点/@资源/$方向，mention 补全 + 后端解析注入双触发）
- 全链路真流式（delta 事件 + 前端逐字渲染 + 流式纯文本/完成后 Markdown）
- 对话前后端双写持久化
- Markdown 渲染
- 全链路真流式（delta 事件 + 前端逐字渲染 + 流式纯文本/完成后 Markdown）
- 对话前后端双写持久化
- Markdown 渲染

### 11.2 风险

| 风险 | 缓解 |
|---|---|
| 三栏在小笔记本挤压 | AI 栏可折叠 + clamp 宽度 |
| marked/hjs 依赖体积 | 只引 hjs common 包 |
| 流式 + Markdown 解析卡顿 | 流式时纯文本，final_done 才解析 |
| 双写不一致 | 后端权威 + 失败重试 + localStorage 兜底 |
| 全链路流式调试复杂 | 工具调用保持非流式（可靠），仅最终回答流式；保留 final_answer 兜底事件 |
| 跨会话搜索性能 | 数据量小用子串匹配；未来量大再加索引 |
| 符号引用与 Markdown 解析冲突 | chip 在 marked 转义后替换；后端预处理先剥离符号再送 LLM |
| LLM 生成标题失败/超时 | 异步生成，失败回退首句截断；不阻塞对话 |
| mention 补全弹层遮挡输入 | 弹层定位在输入框上方，最大高度限制 + 滚动 |
| 引用对象不存在（手打错 id） | 后端 resolve 命中失败时返回空，AI 提示"未找到引用" |
