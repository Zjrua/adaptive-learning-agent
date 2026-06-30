# 设计文档：技能树系统的大模型 Agent 化升级

- **日期**：2026-06-30
- **作者**：zjrua（与 brainstorming 协作）
- **状态**：待实现
- **范围**：把现有「三个无状态单轮生成器」升级为「会调工具、能检索知识、能闲聊、能产飞书文档的后端 Agent loop」

---

## 1. 背景与动机

### 1.1 现状

`skill-tree/backend/ai.py` 当前提供三个 AI 端点：

| 端点 | 能力 | 本质 |
|---|---|---|
| `POST /api/ai/generate-tree` | 贴 JD → 生成整棵技能树 | 单轮 prompt → JSON |
| `POST /api/ai/generate-direction` | 描述 → 生成单方向 | 单轮 prompt → JSON |
| `POST /api/ai/generate-node` | 描述 → 生成节点/知识点 | 单轮 prompt → JSON |

前端 `AiModal.tsx` 是 tab 式表单（新方向 / 补节点），不是对话。

### 1.2 问题（面试视角）

- ❌ **无工具调用**：模型不能自主决定"读图谱 / 查依赖 / 改状态"，全靠前端写死 tab。
- ❌ **无状态感知**：每次生成都不知道用户当前学到了哪、已有哪些节点。
- ❌ **无记忆 / 无多轮**：没有对话上下文，聊一句就忘。
- ❌ **无检索增强（RAG）**：生成知识点时不读已有论文 / 源码，容易编造。
- ❌ **无自我校验闭环**：JSON 解析失败只重试一次，没有"生成→校验→修正"。
- ❌ **无产出**：只生成树节点，不产出笔记 / 复习卡 / 周报等学习文档。

### 1.3 目标

把这套从「生成器」升级为「**Planner-Executor 分层、ReAct 推理循环、工具增强、可产出飞书文档的 Agent**」，且作为 agent 实习面试的可讲故事资产。

## 2. 设计决策（已与用户确认）

| 决策点 | 选择 | 理由 |
|---|---|---|
| 面试亮点 | 工具调用 + RAG + 多步规划 + 文档产出 + 闲聊（全要） | 构成完整 agent 闭环 |
| 架构 | **后端 Agent loop + SSE 流式** | 架构干净，故事顺 |
| 整体走法 | **B. 分层 loop（Planner → Executor → Writer）** | 职责单一，prompt 聚焦，工业界常见范式 |
| 工具协议 | **混合带回退**（原生 function calling 优先，指令式降级） | 适配 5 个供应商差异，工程素养加分 |
| RAG 数据源 | 知识树图谱 + 项目源码 + 论文 + 简历（全要） | 多路召回，结构 + 非结构 + 业务数据 |
| 检索实现 | **向量检索 + 精确检索混合** | 兼顾零依赖原则与 RAG 严肃性 |
| 文档产出 | lark-doc（`lark-cli`） | 已装 v1.0.60，可落地 |

## 3. 总体架构

### 3.1 Agent loop 数据流

```
用户一句话                            后端 /api/agent/chat (SSE)
─────────────                        ──────────────────────────────
"DeepFM学完了,                       ┌─ Session(对话历史 + 用户ID + 图谱快照)
 下一步学啥,                         │
 顺便整理个笔记"                       ▼
        │                     ┌──────────────┐
        ▼                     │   Planner    │  ← system_planner
   前端聊天框                  │  意图分流+拆步 │   判断:闲聊?查询?改图?产文档?
   (AiModal 改造)              └──────┬───────┘
   · 流式渲染 token                   │
   · 工具调用气泡                      ├─ 闲聊/单步查询 → 短路到 Executor(轻量)
   · 思考过程可展开                    │
   · 文档/节点卡片                     └─ 多步/产文档 → 进入完整 loop
                                            │
                                            ▼
                                   ┌──────────────────┐  ReAct 循环 (≤6步)
                                   │    Executor      │  ← system_executor
                                   │  Thought→Tool→   │   工具:RAG检索/图谱读写
                                   │  Observation     │   自校验:JSON schema
                                   └────────┬─────────┘
                                            │ 执行结果/检索片段
                                            ▼
                                   ┌──────────────────┐  仅当需要产文档
                                   │     Writer       │  ← system_writer
                                   │  汇总→飞书文档   │   lark-doc 渲染
                                   └────────┬─────────┘
                                            │
                                            ▼
                                   SSE 流: token + tool_call + doc_card + done
```

### 3.2 关键设计点

- **Session 是 loop 的状态载体**：每个对话有 `messages[]`（多轮历史）、`uid`、`graph_snapshot`（图谱摘要，避免每轮重读）。Session 存内存 dict（单机单用户够用），key = 会话 id。Session 带 TTL（如 30 分钟无活动清除），避免内存泄漏。
- **Planner 做意图分流（短路机制）**：分类 `chat` / `query` / `mutate` / `produce`。前三类短路到 Executor 一步完成；`produce` 才进完整 loop + Writer。
- **Executor 是 ReAct 循环**：`Thought → Action(调工具) → Observation → ... → Final Answer`。最大步数 6，防死循环。
- **Writer 条件触发**：仅 Planner 判定 `produce` 或用户显式要文档时进入。
- **SSE 分事件流**：`thinking` / `tool_call` / `tool_result` / `token` / `doc_card` / `node_proposal` / `error` / `done`。

## 4. 工具协议与工具集

### 4.1 混合工具协议（带回退）

```
构造请求(带 tools 字段)
        │
        ▼
   探测供应商能力
        │
        ├── 成功且返回 tool_calls ──▶ 【原生路径】解析 message.tool_calls[i].function
        │                              得到 {name, arguments(JSON)}
        │
        └── 失败/不支持/无 tool_calls ──▶ 【指令路径】
                                          prompt 注入工具 JSON Schema
                                          模型输出 <tool_call>{...}</tool_call>
                                          正则提取 + JSON 解析 + 容错
```

**统一出口**：两种路径都归一化成 `ToolCall(name, args)` 对象，Executor 不关心来源。

**回退触发条件**：
1. HTTP 报错（供应商不支持 tools 字段）→ 指令路径
2. 响应无 `tool_calls` 且输出含 `<tool_call>` 标记 → 指令解析
3. 指令解析也失败 → 当作纯文本回复（优雅降级，不崩）

### 4.2 工具集（分层暴露）

```
Planner 层 —— 无工具，只输出意图 JSON。

Executor 层（ReAct 循环用）:
  【图谱工具 — 状态感知】
  · get_progress()           → 当前掌握度/已点亮节点/卡住处
  · get_node(node_id)        → 节点详情(任务/验收/依赖)
  · get_path(from, to)       → 两节点间学习路径
  · get_next(node_id)        → 某节点学完该学啥(depends_on 反向)
  · list_nodes(category?)    → 按类别/方向筛节点

  【RAG 工具 — 知识检索】
  · search_knowledge(query, top_k=5)  → 混合检索(源码+论文+简历),带引用片段
  · read_resource(path|url)           → 读具体资源(源码文件/论文链接)

  【图谱变更工具 — 写操作,走预览确认】
  · add_node(parent, spec)            → 生成"加节点"建议(待确认)
  · add_tasks(node_id, tasks)         → 生成"补任务"建议(待确认)
  · toggle_task(tree_id, node_id, task_id, done)  → 勾选(直接执行)

Writer 层（只产文档）:
  · write_doc(title, blocks)            → 渲染飞书文档,返回 doc 卡片
  · suggest_review_cards(node_id)       → 从节点验收生成复习卡(问答对)
```

### 4.3 工具描述格式（双路径共用）

每个工具用统一 JSON Schema 描述，同时喂给原生 function calling 和指令式 prompt：

```python
TOOLS = [
  {
    "name": "search_knowledge",
    "description": "在知识库(开源项目源码、论文、简历素材)中检索与查询相关的内容。返回带来源引用的片段。",
    "parameters": {
      "type": "object",
      "properties": {
        "query": {"type": "string", "description": "检索关键词或问题"},
        "top_k": {"type": "integer", "description": "返回条数,默认5", "default": 5}
      },
      "required": ["query"]
    }
  },
  ...
]
```

指令路径把 `TOOLS` 序列化成文本注入 prompt：
```
你可以使用以下工具。需要调用时,严格输出:
<tool_call>{"name":"工具名","arguments":{...}}</tool_call>
可用工具:
- search_knowledge(query, top_k=5): ...
- get_progress(): ...
```

### 4.4 工具执行约定

- 签名统一 `(args: dict, ctx: Context) -> str`，`ctx` 带 `uid` / `graph` / `session`。
- 返回值是**给模型看的文本**（含 `[1][2]` 引用编号），不是给前端的。
- **写操作安全设计**：`add_node` / `add_tasks` 返回"待确认"结果，前端弹卡片让用户确认后才 apply（复用现有 `/api/ai/apply-direction`）；`toggle_task` 可直接执行。

## 5. RAG 混合检索

### 5.1 四数据源，两类通道

```
┌─────────────────────────────────────────────────────────────┐
│                    检索层(每次 query 多路并发)                 │
├──────────────────┬──────────────────┬───────────────────────┤
│  结构化通道(精确)  │   向量通道(语义)   │   外部通道(按需)        │
│  直接读 JSON      │   embedding+余弦  │   抓取+摘要            │
├──────────────────┼──────────────────┼───────────────────────┤
│ · 知识树图谱      │ · 项目源码(1754py)│ · 论文链接(arXiv/ACM)  │
│   (节点/依赖/     │   按 AST chunk    │   抓 abstract+摘要     │
│    掌握度/成就)   │                  │                       │
│ · 简历素材        │                  │                       │
│   (经历/技能)     │                  │                       │
└──────────────────┴──────────────────┴───────────────────────┘
        │                  │                   │
        └──────────┬───────┴───────────────────┘
                   ▼
        归一化成 [来源]片段 + 相关度分,去重合并 → 带引用编号返回
```

### 5.2 索引构建与存储（守零依赖）

向量索引存 JSONL，不用向量库。embedding 调 OpenAI 兼容 `/embeddings`（DeepSeek/智谱/Qwen 都支持），余弦相似度用 numpy 或纯标准库。

```
data/users/<uid>/rag_index/
├── code_chunks.jsonl      每行: {id, file, symbol, text, vector, mtime}
├── code_meta.json         {built_at, model, dim, count, project_root}
├── paper_cache/           论文抓取后的摘要缓存,按 arxiv id 命名
│   └── 1703.04247.json    {id, url, title, abstract, fetched_at}
└── status.json            索引状态(已索引文件/论文清单 + 时间戳)
```

**索引策略**：
- **源码**：首次构建扫 `../projects/**/*.py`，按 AST 切 chunk（每个顶层 `def` / `class` 一个 chunk + 文件头 docstring）。增量索引：文件 mtime 变了才重算对应 chunk。
- **论文**：懒加载。首次检索到某论文才抓 abstract，缓存到 `paper_cache/`。
- **图谱 / 简历**：不建索引，每次实时读 JSON（数据小，精确查询更快）。

### 5.3 检索时混合排序

`search_knowledge(query)` 内部流程：
1. **结构化**：从图谱 / 简历精确匹配（关键词命中节点名 / 任务标题）。
2. **向量**：query embedding 与 code_chunks 余弦相似度 top-k。
3. **外部**：若 query 含论文 id 或命中节点 resource 链接，抓 abstract。
4. **合并去重 + 重排**：每路分数先各自归一化到 [0,1]（该路无命中则该路分全 0，不参与该条融合），再按 `0.4*结构 + 0.5*向量 + 0.1*外部`（权重可配）融合排序，返回带 `[1][2][3]` 引用编号的文本。

### 5.4 索引构建端点

- `POST /api/rag/build-index`：手动触发重建索引（扫描 + embedding + 写 JSONL）。长任务，后端异步跑，前端轮询进度。
- `GET /api/rag/status`：返回索引状态（已索引文件数 / 论文数 / 时间）。

## 6. Prompt 工程体系

三套 system prompt，分层聚焦。

### 6.1 Planner（意图分流，轻量）

```
你是技能树系统的任务规划器。判断用户意图,输出 JSON 分类。
只输出一个 JSON 对象,不要多余文字。

意图类别:
- "chat": 闲聊/问候/泛泛提问(如"你好""学算法有啥用")
- "query": 查询当前状态/知识(如"我学到哪了""DeepFM是什么")
- "mutate": 修改技能树(如"加个 LightGCN 节点""标记这个学完了")
- "produce": 产出文档/笔记/复习卡(如"整理个笔记""生成复习卡")

用户当前进度摘要:{progress_summary}

用户输入:{user_input}
输出: {"intent": "...", "sub_tasks": ["可选子任务"], "needs_doc": bool}
```

### 6.2 Executor（ReAct 循环，带工具）

```
你是技能树系统的学习助手。用工具回答用户问题。
遵循 ReAct: 先 Thought(思考该用哪个工具),再 Action(调工具),
看到 Observation 后继续,直到能 Final Answer。

可用工具:
{tools_schema_text}

当前用户技能树状态:
{graph_summary}   ← 让模型"看得见"状态,不必每次都调 get_progress

规则:
1. 涉及客观知识,优先 search_knowledge 检索,不要凭空编造。引用用 [1][2]
2. 回答前先判断是否需要查状态(若 graph_summary 不够,调 get_progress/get_node)
3. 改图谱的工具(add_node/add_tasks)只生成建议,最终由用户确认
4. 最多思考 6 步,信息够了就 Final Answer,不要过度调用
5. Final Answer 用中文,带必要的 [引用],可含 markdown

输出格式(严格):
Thought: <思考>
Action: <工具名>
Arguments: <JSON>
--- 或 ---
Thought: <思考>
Final Answer: <给用户的最终回答>
```

### 6.3 Writer（文档产出）

```
你是学习文档撰写器。根据 Executor 收集的素材,生成结构化文档内容。
输出 XML block 序列(飞书文档格式),不要输出其他文字。

支持的 block:
<title>...</title> <h1>/<h2> <p> <code lang="python"> <callout type="info|tip|warning">
<checklist><item checked="false">...</item></checklist> <quote> <bullet>

文档类型模板:
- 学习笔记: 概念→公式/结构→代码片段→易错点(callout)→自测题(checklist)
- 复习卡: 每个知识点一个 Q(quote) + A(p),聚焦"验收"里的"能默写/讲清/手算"
- 周报: 本周完成(checklist)→卡点(callout warning)→下周计划(bullet)

素材(来自检索/图谱):
{materials}

用户要求:{user_request}
输出: 飞书 XML blocks
```

## 7. 前端对话交互

### 7.1 AiModal 改造

现有 tab 式（新方向 / 补节点）改成**多轮对话**，保留"生成 → 预览 → 确认"卡片：

```
┌─ 右下角悬浮 → 展开成对话面板 ──────────────────────────┐
│  ✦ AI 学习助手                              ✕         │
│  ───────────────────────────────────────────────────── │
│  [用户] DeepFM学完了,下一步学啥,顺便整理个笔记          │
│                                                         │
│  [助手] Thought ▸ (可折叠思考过程)                      │
│         · 调用 get_progress → 整体 45%,DeepFM 已掌握    │
│         · 调用 search_knowledge "DeepFM 下游 模型"      │
│           ┌─ 工具气泡: search_knowledge ─────────────┐ │
│           │ [1] DeepCTR-Torch/dcn.py "class DCN..."  │ │
│           │ [2] 论文 DCN (2017) abstract              │ │
│           └──────────────────────────────────────────┘ │
│  [助手流式] DeepFM 之后建议学 DCN/xDeepFM...[1][2]      │
│           ┌─ 📄 文档卡片 ─────────────────────────────┐│
│           │ 《DeepFM 学习笔记》  [预览] [写飞书] [丢弃] ││
│           └──────────────────────────────────────────┘│
│  ───────────────────────────────────────────────────── │
│  [输入框] 输入消息...                          [发送 ▸] │
└─────────────────────────────────────────────────────────┘
```

### 7.2 SSE 事件驱动渲染

| 后端 emit | 前端动作 |
|---|---|
| `thinking` | 追加可折叠"思考"区 |
| `tool_call` | 插入工具气泡（名字 + 参数） |
| `tool_result` | 气泡内填结果摘要 |
| `token` | 逐字追加到助手消息 |
| `doc_card` | 渲染文档卡片（预览 / 写飞书 / 丢弃） |
| `node_proposal` | 渲染"加节点建议"卡片（确认 / 编辑 / 丢弃） |
| `error` / `done` | 错误提示 / 结束本次回复 |

### 7.3 文档卡片 → 飞书

用户点"写飞书" → 前端拿 Writer 产出的 XML blocks → 调后端 `/api/agent/publish-doc` → 后端 `subprocess` 调 `lark-cli docs +create --content '<XML>' --as user` → 返回飞书文档 URL → 卡片变可点击链接。

## 8. 飞书文档产出（lark-doc 集成）

### 8.1 三种文档模板

| 类型 | 触发 | 内容结构（XML blocks） |
|---|---|---|
| **学习笔记** | "整理个 X 的笔记" | `<title>` + `<h1>概念` `<p>` + `<h1>结构/公式` `<code>` + `<callout tip>易错点` + `<h1>自测` `<checklist>` |
| **复习卡** | "生成复习卡" | 每个验收项：`<quote>Q: 能默写 DeepFM 结构?` + `<p>A: ...` + `<callout tip>记忆口诀` |
| **周报** | "本周学习周报" | `<h1>本周完成` `<checklist checked>` + `<h1>卡点` `<callout warning>` + `<h1>下周计划` `<bullet>` |

素材来源：Writer 调用 Executor 已收集的检索片段 + 图谱里的节点 / 验收 / 掌握度。

### 8.2 lark-cli 落地约束

```bash
# 后端 /api/agent/publish-doc 内部执行:
lark-cli docs +create --content '<title>DeepFM 学习笔记</title><p>...</p>' --as user
# → 输出文档 URL,返回前端
```

- 用 `--as user`（按 lark-doc skill 要求）。
- 首次需 `lark-cli auth login`（写入 README 提示用户配置）。
- XML blocks 用 lark-doc skill 的 XML 语法（`<title>/<p>/<code>/<callout>/<checklist>` 等），由 Writer prompt 约束生成。
- **隔离**：文档生成是重操作，Planner 判 `produce` 才进 Writer，不污染对话流。

## 9. 文件改动清单

### 9.1 后端新增 / 修改

```
skill-tree/backend/
├── ai.py                 【保留】原三个生成器函数仍用(被 add_node 等工具复用)
├── agent/                【新增】Agent 核心
│   ├── __init__.py
│   ├── loop.py           Agent loop 主控(Planner→Executor→Writer + SSE 产出)
│   ├── session.py        Session 内存管理(对话历史/图谱快照)
│   ├── prompts.py        三套 system prompt(Planner/Executor/Writer)
│   ├── tools.py          工具定义(JSON Schema) + 注册表
│   ├── tool_runtime.py   工具执行器(签名统一 + 写操作预览)
│   └── protocol.py       混合协议适配(原生 function calling + 指令式回退)
├── rag/                  【新增】RAG 检索
│   ├── __init__.py
│   ├── indexer.py        源码 AST chunking + embedding + 增量索引
│   ├── retriever.py      混合检索(精确+向量+外部)+ 排序融合
│   ├── paper_fetch.py    论文 abstract 抓取 + 缓存
│   └── store.py          JSONL 索引读写
├── larkpub.py            【新增】封装 lark-cli subprocess(create/返回 URL)
└── main.py               【修改】挂载 agent/rag 路由 + SSE endpoint
```

### 9.2 前端修改

```
skill-tree/frontend/src/
├── AiModal.tsx           【重写】tab 表单 → 多轮对话 + SSE 消费 + 卡片渲染
├── ChatMessage.tsx       【新增】对话消息渲染(用户/助手/思考/工具气泡)
├── DocCard.tsx           【新增】文档卡片(预览/写飞书/丢弃)
├── api.ts                【修改】新增 agentChat(SSE)/publishDoc/buildIndex/status
└── types.ts              【修改】新增 AgentEvent / DocCard / ToolCall 类型
```

### 9.3 数据 / 文档

```
skill-tree/data/users/<uid>/rag_index/   【运行时生成】索引文件
docs/superpowers/specs/2026-06-30-llm-agent-design.md   【本文件】
README.md                                【修改】补充 lark-cli auth 配置说明
```

### 9.4 依赖

- `numpy`（向量余弦，**可选加速**）：若已装则用 `numpy.dot` 算余弦，否则退化为纯标准库 `math` 实现。`requirements.txt` 不强制加入，README 注明"装 numpy 可加速检索"。**默认零新增依赖**。
- `lark-cli`（已装 v1.0.60，非 Python 依赖，README 说明）。
- 无向量数据库，无 langchain，无新增重型框架。

## 10. 面试讲法汇总

> 这是本设计的"产品"——一段能在面试里讲 5-10 分钟的完整 agent 故事。

「我把技能树系统的 AI 从三个无状态单轮生成器，升级成一个**Planner-Executor 分层、ReAct 推理循环、工具增强、能产出飞书文档的 Agent**。」

1. **架构**：Planner 做意图分流（带短路，简单任务不过度编排），Executor 跑 ReAct 循环（Thought→Action→Observation），Writer 条件触发产文档。状态用 Session 维持多轮记忆，图谱快照实现状态感知。
2. **工具协议**：做了协议适配层——原生 function calling 优先、指令式 `<tool_call>` 回退，上层看到统一 ToolCall 接口；考虑了供应商差异和降级，5 个 OpenAI 兼容供应商通吃。
3. **工具设计**：工具按 Planner/Executor/Writer 分层暴露；写操作走"生成→预览→确认"防误改；每个工具调用对用户透明可见（SSE tool_call 事件）。
4. **RAG**：多路召回（精确+向量+外部），源码按 AST 语义 chunking，增量索引省成本，混合排序融合三路结果，引用溯源。
5. **prompt 工程**：分层 prompt（Planner 分类 / Executor ReAct / Writer 模板化）；ReAct 强制结构化输出便于解析；Executor 注入 graph_summary 实现状态感知。
6. **工程素养**：守住了后端零依赖原则（向量存 JSONL 不引向量库）；SSE 流式分事件渲染；最大步数保护防发散；优雅降级（协议失败不崩）。
7. **真实产出闭环**：Agent 不只对话，还能产出结构化飞书文档（学习笔记 / 复习卡 / 周报），覆盖完整学习闭环。

## 11. 范围与风险

### 11.1 本次范围（in scope）

- 后端 Agent loop（Planner/Executor/Writer）+ SSE
- 混合工具协议 + 全部工具实现
- RAG 混合检索（源码 AST 索引 + 论文抓取 + 图谱/简历精确检索）
- 前端 AiModal 改对话 + 卡片渲染
- 飞书文档产出（三种模板 + lark-cli 集成）

### 11.2 不在本次范围（out of scope）

- 多用户并发 / 鉴权（仍走现有 X-User-Id，Session 存内存）
- 向量数据库 / langchain（守零依赖）
- 论文全文解析（只抓 abstract + 摘要，不解析 PDF 正文）
- 飞书文档评论 / 权限管理（不在 lark-doc 范围）

### 11.3 风险

| 风险 | 缓解 |
|---|---|
| 各供应商 function calling 行为不一 | 混合协议 + 能力探测 + 指令式回退兜底 |
| embedding 供应商支持不一 | 探测 /embeddings 端点，不支持则该路降级为关键词检索 |
| 源码量大（1754 文件）首次索引慢 | 增量索引 + 进度轮询 + JSONL 流式写 |
| lark-cli 未登录导致 publish 失败 | 后端捕获错误返回前端，前端提示 `lark-cli auth login` |
| Agent loop 步数发散 | 最大步数 6 + Planner 短路 + Final Answer 强制收敛 |
