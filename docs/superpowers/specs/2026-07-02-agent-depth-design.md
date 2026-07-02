# 设计文档:Agent 深度化升级(记忆 / 短路 / 提案 / Reflexion / Prompt / doc→wiki)

- **日期**:2026-07-02
- **作者**:zjrua(与 brainstorming 协作)
- **状态**:待实现
- **范围**:把 `2026-06-30-llm-agent-design.md` 里画好图但浇了一半的楼盖完——补承重柱(记忆/短路/提案),加装修(Reflexion/Prompt 工程),通下水道(doc→wiki 闭环)
- **关联**:`docs/superpowers/specs/2026-06-30-llm-agent-design.md`(原始设计,本文件是其深化与兑付)

---

## 0. 为什么要再写一份 spec

原 spec 设计完整,但代码只兑付了骨架。深挖 `loop.py / prompts.py / tools.py / tool_runtime.py / session.py / main.py / AgentChat.tsx` 后确认:**四个最能讲故事的能力是空心的,另有两个会咬人的代码隐患**。本文件不重画架构,只**精确兑付原 spec 的承诺,并补上原 spec 没写的 Reflexion 闭环与 Prompt 工程细节**。

### 0.1 现状诊断(本设计的全部决策建立于此)

| 能力 | 现状 | 问题 |
|---|---|---|
| SessionStore 多轮记忆 | `session.py` 写好,但 `main.py:447 agent_chat` **从不调用** | 🔴 主线缺失 |
| 前端历史透传 | `AgentChat.tsx:100` 只发当前文本,历史一条不带 | 🔴 主线缺失(前后端协同) |
| Planner 短路分流 | `loop.py:88` 算了 intent,**只用 needs_doc**;chat/query/mutate 全进 6 步 ReAct | 🟠 设计未兑付 |
| `node_proposal` 事件 | `types.ts:108` 已定义,但 `loop.py` 从不 emit;`add_node` 只返回文字 | 🔴 主线缺失 |
| 自校验/Reflect | 无。无 schema 校验、无失败重写、无答案校验 | 🔴 主线缺失(Reflexion 是加分项) |
| Prompt few-shot | `prompts.py` 三套**零示例纯规则**;`parse_react` 用 `split()[0]` 抓 action,脆弱 | 🟠 质量+健壮性 |
| Writer 三模板 | `_run_writer` 把 `doc_type` **写死 "note"**,复习卡/周报形同虚设 | 🟡 质量薄 |
| lark doc→wiki 沉淀 | `publish-doc` 只 `docs +create` 单篇,无 wiki 归档;URL 正则只匹配 `/docx/` | 🟡 闭环缺一环 |

### 0.2 三个代码隐患(改动顺手修)

1. **`loop.py:45` `parse_react` 脆弱**:`_after(text,"Action:").split()[0]`——`Action: get_progress（查进度）` 会变成 `get_progress（查进度）`,`Action:\nget_progress` 会变空。新 prompt 上线后调用更频繁,必重构。
2. **`loop.py:147` chat intent 仍二次调模型 + 前缀剥离**:chat 本可在 Executor 首步直答,短路重构顺带简化。
3. **`ai.py:87` 死代码**:连写两个 `except Exception`,第二个永不执行。既然要碰 ai.py(add_node 复用),顺手删。

---

## 1. 架构决策(已与用户确认方向 A:agent 能力深做 + 飞书 doc→wiki 单点闭环)

| 决策点 | 选择 | 理由 |
|---|---|---|
| 总体走法 | 方案 A:agent 四能力做扎实 + 飞书 doc→wiki 一个闭环 | 面试故事聚焦,可实现可演示;飞书 task/base 进 Future Work |
| 记忆架构 | **前端发历史 + 服务端无状态**,SessionStore 改做 graph 快照缓存 | 解耦 UI 会话与 agent 记忆,可扩展,数据天然在客户端 |
| Planner 短路 | chat 单步直答;query/mutate 走 ReAct;produce 走 ReAct+Writer | 省 token,兑付原 spec §3.2 |
| 提案闭环 | 工具能产事件;node_proposal 结构化卡片;生成→预览→确认 | 兑付原 spec §4.4 写操作安全设计 |
| 自校验 | 双层:结构化 schema 校验(失败重写一次)+ Reflexion 答案校验(最多 1 轮) | 区分度最高的 agent 技巧 |
| Prompt 工程 | 三套加 few-shot + 正则化解析 + 黄金用例回归测试 | 固化质量,防回归 |
| doc 沉淀 | `wiki +node-create`(优先)或 `docs +create`→`wiki +move`;可配 space_id | 产出即沉淀、可回溯 |

---

## 2. 多轮记忆(架构决策详解)

### 2.1 为什么不用 SessionStore 当记忆载体

原 spec §3.2 设计 SessionStore 为"agent 记忆载体",但深挖发现两处矛盾:

1. **多会话冲突**:前端 `AgentChat.tsx` 已管理多个 `ChatSession`(UI 会话)并持久化到 `chat_history.json`。SessionStore 按 `uid` 单 key 存记忆,用户在多个会话间切换会串记忆。要修就得 key=`uid+session_id`,引入 TTL/淘汰/一致性管理。
2. **数据冗余**:前端早已有每会话的完整 user/assistant 文本(`messages[]`),服务端再存一份是重复。

### 2.2 决策:前端发历史,服务端无状态

- 前端 `api.agentChatStream(message, history, cb)`:`history = current.messages.slice(-12).map(m => ({role, content}))`(最近 6 轮 user+answer,丢掉 events/Observations,避免上下文膨胀)。
- 后端 `AgentChatReq` 增 `history: list = []`;`run_agent(ctx, message, history=..., ...)` 把 history 前置注入 Executor 的 messages。
- **讲法**:agent 的"工作记忆"由客户端按上下文窗口裁剪后提供,服务端无状态,可水平扩展。Observations(工具结果)不跨轮保留——学习场景的追问很少需要上一轮的原始检索片段,且重检索成本低;若未来需要,再加服务端摘要层(YAGNI,先不做)。

### 2.3 SessionStore 的新职责:graph 快照缓存

不删 SessionStore(原 spec 已建),改给它一个真实且有用的职责:

- `main.py:_build_ctx` 每条消息都重算 `compute_layout` + 所有节点的 `node_mastery`/`node_status`。对中等规模树(50-100 节点)是毫秒级,但热路径上仍可省。
- SessionStore 按 `uid` 缓存 graph 快照,TTL 30s(图谱变更频率低;用户勾选任务后下次请求自然失效重算)。
- 这给 SessionStore 一个清晰、可测、可解释的角色,而不是让它当被遗忘的死代码。

### 2.4 接口改动

- 前端 `api.ts`:`agentChatStream(text, history, cb)` 签名增 `history`。
- `AgentChat.tsx:send`:构造 history 一并发送。
- `main.py:AgentChatReq`:增 `history: list = []`。
- `agent/loop.py:run_agent`:增 `history: list[dict] | None = None`,前置注入。

---

## 3. Planner 短路分流

### 3.1 分流规则

Planner 返回 `intent` 后(逻辑不变,仍输出 JSON 分类),按 intent 走不同路径:

| intent | 路径 | 说明 |
|---|---|---|
| `chat` | **单步直答** | 一次 LLM 调用,不挂工具,不进 ReAct。带 history。顺带干掉 `_stream_final` 的二次调用 + 前缀剥离 |
| `query` | ReAct 循环(≤6) | 可能要 get_progress/search_knowledge/get_node |
| `mutate` | ReAct 循环(≤6) | add_node/add_tasks/toggle_task,写操作走提案 |
| `produce` | ReAct 循环(≤6) + Writer | 收素材后产飞书文档 |

### 3.2 chat 短路的实现

```
intent == "chat":
  sys = SYS_CHAT_DIRECT  (要求直接回答,中文,可用 markdown,不要 ReAct 格式)
  messages = [sys] + history + [{role:user, content:user_input}]
  非流式拿回答 → 直接 chunk 成 delta 事件流式吐给前端 → final_done
```

这是一次 LLM 调用,比当前"先 ReAct 一步拿 Final Answer 再二次调模型流式 + 前缀剥离状态机"简单一个量级,且省一次调用。

> **关于"流式"的统一口径**(本设计的全局约定):所有最终答案都是**先非流式拿到完整文本,再 chunk 成 delta 事件**输出。这统一了 chat 直答 / query / produce 三条路径,彻底移除 `_stream_final` 的"二次模型调用 + ReAct 前缀剥离状态机"——既不省那次调用(本来就是第二次),又增加前缀误判风险。代价:回答首字延迟略增(等整段生成)。对学习助手场景可接受;若未来要追求首字延迟,再上真流式(YAGNI)。`FakeChat` 桩的 stream 分支保留以测未来路径,但主流程不再依赖。

### 3.3 短路的容错

Planner 本身可能失败(供应商返回非 JSON)。已有兜底:`_safe_intent` 失败回退 `query`(走 ReAct,安全)。保持不变。

---

## 4. node_proposal 提案闭环

### 4.1 核心改动:工具能产事件

当前 `execute_tool(name, args, ctx) -> str`。升级为:

```python
def execute_tool(name, args, ctx) -> ToolResult:
    # ToolResult = {"text": str, "events": list[dict]}
```

- `text`:给模型看的简短文本(如"已生成节点建议,请用户在前端确认。")。
- `events`:要 emit 的 SSE 事件(如 `{"type":"node_proposal","node":{...}}`)。

`loop.py` 在每次工具调用后:
```python
result = execute_tool(action, args, ctx)
yield {"type": "tool_result", "action": action, "content": result["text"]}
for ev in result.get("events", []):
    yield ev
observation = result["text"]   # 模型看到的是 text
```

### 4.2 add_node / add_tasks 产提案

- `add_node`:
  1. 调 `ai.generate_node(cfg, description, node_id="", existing_ids=...)` 生成结构化 node JSON。
  2. schema 校验(见 §5.1),失败重写一次。
  3. emit `{"type":"node_proposal","node":<norm_node>, "mode":"new_node"}`。
  4. text 返回"已生成新节点《{name}》建议,请在卡片上确认。"
- `add_tasks`:
  1. 调 LLM 为指定 node_id 生成补充 tasks/verify。
  2. emit `{"type":"node_proposal","node_id":..., "tasks":[...], "mode":"add_tasks"}`。
  3. text 返回"已为 {node} 生成 N 条补充任务,请确认。"
- `add_node`/`add_tasks` 需要 `cfg`,故 `Context` 增 `cfg: dict` 字段。

### 4.3 前端提案卡片

- `node_proposal` 事件→渲染卡片:`《DeepFM》 含 3 任务 2 验收 [应用][编辑][丢弃]`。
- **应用**:调新端点写入树文件(见 §4.4),成功后刷新图谱(`api.graph()`)。
- **编辑**:展开 node JSON 文本框,改完再应用。
- **丢弃**:关闭卡片。

### 4.4 新增 apply 端点

- `POST /api/ai/apply-node {tree_id?, node}`:把 node 插入指定 tree 的某 branch(无 tree_id 则按 depends_on 命中或创建新单节点 tree 文件)。复用 `_find_tree_file` + `_apply_done` 同款 tree 变换逻辑。
- `POST /api/ai/apply-tasks {tree_id, node_id, tasks}`:向 node 追加 tasks/verify。

两个端点各约 20 行,均写回 JSON 文件并返回新 graph(复用 `get_graph` 逻辑)。

---

## 5. 自校验 / Reflexion

### 5.1 结构化输出校验(给 add_node/add_tasks)

`ai._norm_node` 已做基本规范化。新增轻量校验器:

- 必填:`id`(非空)、`name`(非空)、`tasks`(list,可为空)。
- `id` 合法:`^[a-z0-9_]+$`(英文短 id,与现有 node id 风格一致);不合法→自动 slugify。
- `depends_on` 引用的 id 若不在 existing_ids,记 warning(不阻塞,前端编辑可修)。

失败时:把校验错误拼进 retry_prompt,重调一次 `generate_node`(复用 `ai._call_json` 已有的重试机制思路)。仍失败则 emit proposal 卡片但标 `"incomplete": true`,前端提示用户编辑。

### 5.2 Reflexion 答案校验(给 query/produce)

ReAct 产出 Final Answer 草稿后,插入 `_reflect` 步:

```
输入:{user_question, observations_summary, draft_answer}
sys_reflect:
  你是校验器。判断 draft_answer 是否真的回答了 user_question,且与 observations 一致(无编造)。
  只输出 JSON: {"ok": bool, "gap": "若不 ok,缺什么/错什么;ok 则空串"}
决策:
  ok=true → 接受草稿,正常流式输出。
  ok=false 且 Executor 还有步数(且 reflect 未用过)→
    把 draft 当作已有回答,注入 "草稿遗漏: {gap}。请用工具补充后给最终回答。" 续跑 ReAct(最多再 1 轮)。
  ok=false 且无步数/已 reflect 过 → 接受草稿(优雅降级,不卡死)。
```

### 5.3 成本与封顶

- Reflect = +1 次 LLM 调用,仅 query/produce,每轮最多 1 次。chat 不 reflect。
- 与 max_steps=6 叠加:最坏 query 路径 = 6 步 ReAct + 1 reflect + 1 续跑,可控。
- Reflect 用低 temperature(0.2),输出严格 JSON,失败回退 `ok=true`(不阻塞主流程)。

### 5.4 流式时序(与 §3.2 统一口径)

Reflect 在输出**之前**做。流程:
```
ReAct 循环 → 拿到 Final Answer 草稿(非流式) → Reflect → (ok=false 且有步数→续跑 ReAct 1 轮→拿新草稿)
        → 把最终确定的答案文本 chunk 成 delta 事件吐给前端 → final_done
```

即"先想清楚再开口"。**关键:Reflect 校验的就是最终交付的那份草稿**——不在中间二次调模型重新生成答案(否则 Reflect 校验的是 A、交付的是 B,自相矛盾)。对照旧实现 `_stream_final`:它是"拿草稿→丢弃→二次调模型重写→流式",本设计改为"拿草稿→Reflect→直接 chunk 输出草稿",省一次调用、消除前缀剥离风险、让 Reflect 名副其实。

**Executor few-shot 的配合要求**(见 §6.1):示例必须训练模型把 `Final Answer:` 写成**完整、可直接交付**的回答(含 markdown 排版),因为这份文本会被原样 chunk 输出,不再有二次润色机会。

---

## 6. Prompt 工程

### 6.1 三套 prompt 加 few-shot

- **Planner**:加 4 个示例覆盖 chat/query/mutate/produce 各一,固化分类边界。
- **Executor**:加 2 个 ReAct 示例——(a) 该 search 的客观知识问题,(b) graph_summary 已够、直接 Final Answer 的状态查询。加"工具选择指引"小节:何时该调 search_knowledge、何时 get_progress、何时直接答。**示例里的 Final Answer 必须是完整可交付文本**(含 markdown),因为 §5.4 约定它会被原样 chunk 输出、不再二次润色。
- **Writer**:三模板各自给一个完整 XML block 示例(笔记/复习卡/周报),Writer 按 `doc_type` 选模板。

### 6.2 ReAct 解析正则化(重构 parse_react)

替换 `split()[0]`,改为:

- Action 行:`Action:\s*(\w+)` 取第一个 word(容错后续中文注释/括号)。
- Arguments:Action 行之后到下一个 `Thought:`/`Final Answer:`/EOF 之间的内容,`json.loads`(容错多余文字)。
- Final Answer:`Final Answer:\s*([\s\S]*)`。
- 都不匹配→当作 final(原样,优雅降级)。

`tests/test_loop.py` 加边界用例:`Action: get_progress（查进度）`、`Action:\nget_progress`、多行 JSON Arguments。

### 6.3 Prompt 回归测试

`tests/test_prompts.py`:
- Planner 4 例:输入→期望 intent。
- Executor 2 例:输入→期望首个 Action 或 Final Answer。
- parse_react 边界用例集合。
用 `FakeChat` 桩,断言行为不依赖真实模型。这是"prompt 工程不是玄学,有回归保护"的讲法。

---

## 7. lark-doc→wiki 沉淀闭环

### 7.1 两条实现路径(实现时按 skill 文档确认)

读 `lark-wiki/references/lark-wiki-node-create.md` 与 `lark-doc/references/lark-doc-create.md` 确认:
- **路径 1(优先)**:`lark-cli wiki +node-create --space <id> --content '<XML>'`——若该 shortcut 接受 content,一步在 wiki 空间内建文档节点,返回 wiki URL。
- **路径 2(回退)**:`lark-cli docs +create --content '<XML>'` 拿 docx token → `lark-cli wiki +move --source-doc <token> --space <id>` 移入 wiki。

任一路径都要:
- 用 `--as user`(两个 skill 都要求)。
- content 用 XML block 语法(`<title>/<p>/<code>/<callout>/<checklist>/<quote>/<bullet>` 等),由 Writer prompt 约束。
- 实现前 MUST 先 Read `lark-shared/SKILL.md`(认证) + 对应 create/move reference。

### 7.2 wiki_space_id 配置

- 用户配置项 `wiki_space_id`(存 `llm_config.json` 或单独 `lark_config.json`)。
- 新增设置入口:列空间(`lark-cli wiki +space-list --as user --format json`)→ 用户选一个→存 id。
- 有 space_id:产出文档自动归档到"学习知识库",返回 wiki URL。
- 无 space_id:`publish-doc` 仍返回 docx URL(优雅降级,不阻塞)。

### 7.3 larkpub.py 改动

- `publish_doc(xml, title, wiki_space_id=None) -> {url, kind:"wiki"|"docx"}`。
- wiki_space_id 有→走 §7.1;无→现有 `docs +create`。
- `parse_doc_url` 正则修成同时匹配 `/docx/` 和 `/wiki/`。
- `_run` 超时从 120s 提到 180s(wiki 操作更慢)。

### 7.4 Writer 三模板真正差异化

`_run_writer` 不再写死 "note":

- Planner 的 `sub_tasks` 或显式关键词决定 `doc_type`:含"复习/背/默写"→review;含"周报/本周/总结"→weekly;否则 note。
- 素材不只喂 Observation 文本,还喂:相关节点的结构化信息(name/tasks/verify/pct)+ RAG 命中片段(Writer 可显式调一次 search 收素材,或复用 Executor 已收集的)。
- emit `{"type":"doc_card","doc_type":..., "content":<XML>, "title":...}`,前端卡片显示类型图标。

---

## 8. 前端改动

- `api.ts`:`agentChatStream(text, history, cb)`;新增 `applyNode`、`applyTasks`、`listWikiSpaces`、`setWikiSpace`。
- `AgentChat.tsx`:`send` 构造并带 history;消费 `node_proposal` 事件渲染卡片。
- 新组件 `NodeProposalCard.tsx`:`[应用][编辑][丢弃]`,应用调 apply 端点后刷新图谱。
- `DocCard.tsx`:显示 doc_type 图标 + wiki/docx 标识。
- `SetupPanel.tsx`(或设置区):wiki space 选择器。
- `types.ts`:`AgentEvent` 的 `node_proposal` 细化字段;新增 apply 请求/响应类型。

---

## 9. 后端文件改动清单

```
skill-tree/backend/
├── agent/
│   ├── loop.py        【改】history 注入 / Planner 短路 / Reflect / 工具事件转发 / chat 直答
│   ├── prompts.py     【改】三套加 few-shot + 工具选择指引 + SYS_CHAT_DIRECT + SYS_REFLECT
│   ├── tool_runtime.py【改】execute_tool 返回 (text, events);add_node/add_tasks 产提案 + 校验
│   ├── tools.py       【改】补 spec 缺失工具 get_path/list_nodes/read_resource(可选,见 §11)
│   └── protocol.py    【不动】
├── session.py         【改】改做 graph 快照缓存(get_graph_snapshot/set,TTL)
├── main.py            【改】AgentChatReq.history / 接 SessionStore 缓存 / apply-node / apply-tasks / wiki space 端点
├── ai.py              【改】删死代码;抽出 node 校验器供 add_node 复用
├── larkpub.py         【改】publish_doc 支持 wiki 归档 + URL 正则修正
└── tests/
    ├── test_loop.py       【改】history/短路/Reflect/提案/parse_react 边界
    ├── test_prompts.py    【改】few-shot 回归黄金用例
    └── test_tool_runtime.py【改】execute_tool 返回结构 + 提案事件
```

---

## 10. 测试矩阵

| 模块 | 用例 | 断言 |
|---|---|---|
| 记忆 | history 非空时被注入 Executor messages | messages 前置含 history |
| 短路 | chat intent 不触发 ReAct、只 1 次调用 | events 无 tool_call |
| 短路 | query intent 走 ReAct | 有 tool_call/tool_result |
| 提案 | add_node 产 node_proposal 事件 + 校验 | events 含 node_proposal,node 合法 |
| 提案 | node schema 非法→重写一次 | FakeChat 被调两次 |
| Reflect | ok=false 且有步数→续跑 | 出现 gap 注入,续跑一轮 |
| Reflect | ok=false 无步数→接受草稿 | 不卡死,有 final |
| parse_react | Action 带中文注释/换行 | action 正确提取 |
| Prompt | Planner 4 分类 | intent 正确 |
| larkpub | wiki_space_id 有→调 wiki | url kind=wiki |
| larkpub | URL 正则匹配 /docx/ 和 /wiki/ | 两组都命中 |

---

## 11. 范围与 Future Work

### 11.1 本次 in scope

- 多轮记忆(前端发历史 + SessionStore graph 缓存)
- Planner 短路(chat 直答)
- node_proposal 提案闭环(add_node/add_tasks + apply 端点 + 前端卡片)
- 自校验(schema 校验 + Reflexion)
- Prompt 工程(few-shot + 正则解析 + 回归测试)
- doc→wiki 沉淀闭环 + Writer 三模板差异化

### 11.2 不在本次(out of scope / Future Work)

- 飞书 lark-task(学习任务推送)、lark-base(学习看板)——讲得出但不实现,避免铺太开稀释 agent 故事
- 服务端跨会话 Observation 记忆 / 自动摘要(YAGNI,客户端发历史已够)
- spec §4.2 里缺失的 get_path/list_nodes/read_resource 工具(可本轮顺手补,优先级低)
- 多用户并发鉴权(仍走 X-User-Id)

### 11.3 风险

| 风险 | 缓解 |
|---|---|
| Reflect 增加延迟/成本 | 仅 query/produce,封顶 1 轮,失败回退 ok=true |
| few-shot 让 prompt 变长 | 示例精简(每套 2-4 例),监控 token |
| wiki +node-create 是否接受 content 待确认 | 实现时先读 skill 文档;不支持则走 create+move 回退 |
| lark-cli 未登录致 publish 失败 | 后端捕获返回前端,提示 `lark-cli auth login`;doc→wiki 失败回退 docx |
| add_node 生成的 id 冲突 | slugify + 校验 + 前端编辑可改 |

---

## 12. 面试讲法(5-10 分钟)

> 「我把技能树 agent 从'能调工具的 ReAct 骨架'升级成'有记忆、会短路、能自我校验、产出可沉淀'的完整 agent——而且每个设计点都有明确的工程取舍。」

1. **记忆**:没盲目用服务端 Session 存全部对话。判断出 UI 会话与 agent 记忆是两个东西,选了"客户端按上下文窗口裁剪后发历史、服务端无状态"——可扩展、不串会话;SessionStore 改做 graph 快照缓存,各司其职。**取舍讲得清楚**。
2. **短路**:Planner 分类后 chat 直答一步出,不滥用 ReAct。**知道什么时候不该用 agent**。
3. **提案闭环**:写操作不直接改盘——工具产结构化 node_proposal 卡片,用户确认才 apply。**防误改的安全设计**。
4. **Reflexion**:ReAct 答完加一步自我校验,发现遗漏就续跑(封顶 1 轮)。**比基础 ReAct 高一阶,知道 Reflexion 这套范式并能落地**。
5. **Prompt 工程**:三套分层 prompt 带 few-shot,ReAct 解析正则化容错,配黄金用例回归测试。**不是玄学调 prompt,是工程化**。
6. **doc→wiki 沉淀**:Agent 不止对话,还把笔记/复习卡/周报产出归档到一个飞书学习知识库,端到端可演示。**真实产出闭环**。
