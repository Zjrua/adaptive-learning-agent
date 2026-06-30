# 设计文档：AI 对话区改造（独立常驻 + 记忆 + Markdown）

- **日期**：2026-06-30
- **状态**：待实现
- **范围**：把 AI 从右下角临时悬浮 FAB 改造为系统一等公民——响应式独立对话区（桌面三栏常驻 / 移动独立页）、对话历史前后端双写持久化、Markdown 渲染。

---

## 1. 背景与动机

### 1.1 现状

`AgentChat.tsx` 当前是右下角悬浮 FAB 弹出的小窗：
- 对话记录用 `useState` 持有，**关掉 FAB 或刷新即丢失**。
- 挤在屏幕角落，空间局促。
- AI 是整个系统里唯一的「浮窗孤岛」——其他功能（技能树/个人信息/简历模板/果实）都是侧栏导航下的一等 panel 页面，唯独 AI 游离在外。
- `final_answer` 是纯文本，Agent 返回的 markdown（标题/列表/代码块）原样显示。

### 1.2 目标

三个诉求：
1. **对话有记录、能持久化**：关窗/刷新不丢，跨设备同步。
2. **AI 独立成系统一等公民**：不再是角落浮窗，而是右侧永远常驻的独立交互部分，与侧栏各板块平级。
3. **Markdown 渲染**：标题/列表/代码块/引用/表格正确呈现，符合玉青宝石工坊美学。

### 1.3 设计决策（已与用户确认）

| 决策点 | 选择 | 理由 |
|---|---|---|
| 布局形态 | **响应式**：桌面三栏（侧栏+主区+常驻 AI 窗口）；移动端 AI 作侧栏独立项（🤖）切全屏页 | 桌面边用边问、移动不挤压 |
| 对话持久化 | **前后端双写**：后端 `chat_history.json` 权威 + 前端 localStorage 缓存 | 跨设备同步 + 首屏快 |
| Markdown | **marked + DOMPurify + highlight.js** | 业界标准、安全、生态好 |

## 2. 总体布局（核心）

### 2.1 桌面端（≥820px）：三栏，AI 永远常驻

```
┌─侧栏─┬────主区(随侧栏导航变)────┬──AI常驻窗口──┐
│ 🌳   │                          │ ✦ AI助手  ◂ │ ← 可折叠
│ 👤   │  当前板块内容:            │ ─────────── │
│ 📄   │  · #tree → 知识图谱 DAG   │ [用户]      │
│ 🍎   │  · #profile → 个人信息    │ 我学到哪了  │
│      │  · #templates → 简历模板  │             │
│      │  · #fruit → 果实展示      │ [助手] 💭   │
│      │                          │ 🔧get_progress│
│      │  ← 切换侧栏,主区变,       │ 你整体45%…  │
│ ⚙️   │    但 AI 右栏不动!        │             │
│ 45%  │                          │ ─────────── │
└──────┴──────────────────────────┤ [输入框][▸] │
                                  └─────────────┘
```

**关键**：`<App>` 的 grid 从 `256px 1fr` 变成 `256px 1fr clamp(320px, 28vw, 440px)`。AI 栏是 App 的**直接子元素**，不嵌在任何路由 panel 内——切换侧栏板块时它纹丝不动，对话记录天然保留（组件不随路由 unmount）。

- **可折叠**：AI 栏顶部 ◂ 按钮收成一条窄边（只留 ✦ 图标），点开恢复。折叠状态用 localStorage 记忆。
- **宽度**：`clamp(320px, 28vw, 440px)`，技能树区自适应剩余。

### 2.2 移动端（<820px）：AI 作侧栏独立项，切全屏页

```
┌─侧栏(横向)──────────────────────────────────┐
│ 🌳技能树  👤信息  📄模板  🍎果实  🤖AI  ⚙️   │  ← 🤖 加进侧栏导航
└──────────────────────────────────────────────┘
点 🤖 → 全屏 chat 页面(#chat)
点其他 → 对应板块,桌面常驻栏不显示
```

移动端空间有限，AI 退成独立页面；桌面端的常驻栏在移动端不渲染。

### 2.3 一个组件两种容器

`<AgentChat>` 组件逻辑不变，靠 CSS 控制父容器：
- 桌面：挂在 App 右栏（常驻，class `ai-dock`）
- 移动：挂在 `#chat` 路由的 panel（全屏，class `ai-page`）

## 3. 路由与导航

### 3.1 侧栏导航

侧栏导航按断点区分：
- **桌面侧栏**：保持 4 项（🌳👤📄🍎）+ 设置。**不加 🤖 项**——因为 AI 栏永远常驻在右侧，无需导航切换。
- **移动端横向侧栏**：多一个 🤖AI 项，点它切到 `#chat` 全屏页（移动端无常驻栏，只能这样进 AI）。

```
路由: #tree(默认) / #profile / #templates / #fruit / #chat(移动端用) / #setup / #settings
#chat 路由在桌面端也可访问(切到纯对话全屏),但主要服务移动端
```

### 3.2 AI 在不同断点/路由下的行为

| 断点 | AI 渲染位置 | 切换侧栏板块时 |
|---|---|---|
| 桌面 (≥820px) | App 右栏常驻（所有路由都在） | AI 栏不动，对话保留 |
| 移动 (<820px) | 仅 `#chat` 路由全屏 | 离开 `#chat` 即隐藏 |

### 3.3 删除旧 FAB

移除 App 里的右下角悬浮 ✦ 按钮及其相关逻辑（`showAi` state、`.ai-fab` 样式）。

## 4. 对话记忆（前后端双写）

### 4.1 数据流

```
用户发消息
   │
   ▼
AgentChat (前端) ──乐观更新 UI──▶ 立即显示用户气泡
   │
   ├──▶ POST /api/agent/chat (SSE) ──▶ 后端 Agent loop
   │                                       │
   │   ◀── SSE 事件流 (thinking/tool/final/done)
   │                                       │
   ▼                                       ▼
事件累加到 messages                   后端 loop 结束
   │                                       │
   ▼                                       ▼
done 事件后                          POST /api/chat/sync
   │                                 (前端发回完整对话,后端覆盖存)
   ▼                                       │
localStorage 写入 chat_<uid>               │
(缓存,加速首屏)                             ▼
                                   data/users/<uid>/chat_history.json
```

### 4.2 后端存储格式

`data/users/<uid>/chat_history.json`：

```json
{
  "messages": [
    {"role":"user","content":"我学到哪了","ts":"2026-06-30T14:00:00"},
    {"role":"assistant","content":"你整体45%…","events":[…],"ts":"2026-06-30T14:00:05"},
    ...
  ],
  "updated_at": "2026-06-30T14:01:00"
}
```

### 4.3 新增端点

- `GET /api/chat/history` → 返回 `{messages, updated_at}`（首屏加载，后端权威）。
- `POST /api/chat/sync` → body `{messages}`，后端覆盖写 `chat_history.json`，返回 `{ok}`。

### 4.4 前端缓存策略

- **首屏**：先读 localStorage `chat_<uid>` 秒开 → 再 `GET /api/chat/history` 校正（后端权威，覆盖本地）。
- **每轮 done 后**：更新 localStorage + `POST /api/chat/sync`。
- **失败处理**：sync 失败不阻塞（本地仍保留），下次重试；网络错误时 UI 仍可用。
- **用户切换**：`onUserChanged` 时清 localStorage 缓存 key，重拉。

### 4.5 面试讲法

前后端双写、后端权威源 + 前端缓存降低首屏延迟、乐观更新提升体验、最终一致（sync 失败可重试不丢数据）。

## 5. Markdown 渲染

### 5.1 组件

新建 `Markdown.tsx`，封装 `marked` + `DOMPurify` + `highlight.js`：

```tsx
// ChatMessage 里 final_answer 和 DocCard 预览都用它
<Markdown content={msg.content} />
// 内部: marked.parse(content) → DOMPurify.sanitize(html) → dangerouslySetInnerHTML
// 代码块: highlight.js 自动高亮(只引常用语言包控体积)
```

### 5.2 安全

`marked` 默认不转义 HTML，**必须配 DOMPurify.sanitize** 防 XSS。highlight.js 只引入 `common` 语言包（约 10 种）控制体积，避免全量引入。

### 5.3 样式融入美学（玉青宝石工坊）

新增 `.md` 样式块，渲染出的 markdown 符合既有调色板：

| 元素 | 样式 |
|---|---|
| `h1/h2/h3` | Fraunces 衬线，玉青色 `--jade`，左侧玉青竖线（复用 `.sb-item.active::before` 视觉语言） |
| 行内 `code` | JetBrains Mono，`--moss-2` 底，玉青文字 |
| ` ``` 代码块 ``` ` | 深墨底 `--ink-2` + 玉青边框 `--glass-border` + 左侧色带 + highlight.js 高亮 |
| `blockquote` | 左玉青竖线 + `--fg-dim` 斜体 |
| `ul/li` | 玉青圆点 `--jade` |
| `table` | 玉青表头底 `--moss-2`，玉青边框 |
| `a` | 玉青色 + 下划线 |
| `strong` | `--gold` 金芽色强调 |

## 6. 文件改动清单

```
frontend/src/
├── AgentChat.tsx      【重写】悬浮窗 → 响应式对话区(常驻 dock / 全屏 page)
├── ChatMessage.tsx    【改】final_answer 用 <Markdown> 渲染
├── Markdown.tsx       【新】marked + DOMPurify + highlight.js 封装
├── api.ts             【改】新增 chatHistory()/chatSync()
├── types.ts           【改】ChatMessage 加 ts 字段; 新增 ChatHistory 类型
├── App.tsx            【改】三栏 grid; 侧栏加 🤖(移动); AI 栏常驻; 删 FAB; 加 #chat 路由
└── index.css          【改】三栏响应式 + .md 样式 + AI 栏样式

backend/
└── main.py            【改】新增 GET /api/chat/history + POST /api/chat/sync

依赖: npm i marked dompurify highlight.js (+ @types)
```

## 7. 范围与风险

### 7.1 本次范围（in scope）

- 三栏响应式布局（桌面常驻 AI / 移动独立页）
- 对话前后端双写持久化
- Markdown 渲染（marked + DOMPurify + highlight.js）
- 删除旧 FAB

### 7.2 不在范围（out of scope）

- 多会话/多对话切换（当前单一线性对话历史）
- 对话搜索/导出
- 流式 token 逐字渲染（当前是 final_answer 一次性，已够用）

### 7.3 风险

| 风险 | 缓解 |
|---|---|
| 三栏在小笔记本（820-1100px）挤压技能树 | AI 栏可折叠 + `clamp` 宽度自适应；用户可收起 |
| marked 依赖体积 | 只引 highlight.js common 包；marked 本身 ~12KB gzip |
| 双写不一致（sync 失败） | 后端权威 + 失败重试 + localStorage 兜底，最终一致 |
| DOMPurify 配置错误致 XSS | sanitize 默认配置已够；代码块经 highlight 转义 |
| 旧 FAB 删除后用户找不到 AI | 桌面常驻栏始终可见；移动端 🤖 导航项明确 |
