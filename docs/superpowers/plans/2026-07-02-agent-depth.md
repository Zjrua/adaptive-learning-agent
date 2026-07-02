# Agent 深度化升级 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把技能树 agent 从「能调工具的 ReAct 骨架」升级成「有记忆、会短路、能提案确认、会自我校验、产出可沉淀到飞书 wiki」的完整 agent。

**Architecture:** 沿用现有 Planner→Executor→Writer 三层。改动按依赖顺序推进:先重构数据结构(execute_tool 返回值、parse_react 解析),再逐层叠加能力(history 记忆 → Planner 短路 → 提案闭环 → Reflexion → Prompt few-shot → doc→wiki)。每一步 TDD,全流程零新增 Python 依赖。

**Tech Stack:** Python 标准库(urllib/subprocess/re/dataclasses)、FastAPI、SSE、lark-cli subprocess、React+TypeScript 前端。

**Spec:** `docs/superpowers/specs/2026-07-02-agent-depth-design.md`

---

## 文件结构(改动落点)

**后端(agent 核心):**
- `agent/tool_runtime.py` — `execute_tool` 返回值从 `str` 升级为 `ToolResult(dict)`;`add_node`/`add_tasks` 产 `node_proposal` 事件 + schema 校验;补 `_validate_node`。
- `agent/loop.py` — history 注入;Planner 短路(chat 直答);工具事件转发;Reflexion;移除 `_stream_final`,改为统一「拿全文本→chunk 成 delta」。
- `agent/prompts.py` — 三套加 few-shot;新增 `SYS_CHAT_DIRECT`、`SYS_REFLECT`;Writer 按 doc_type 选模板。
- `agent/session.py` — 改做 graph 快照缓存(`get_snapshot`/`set_snapshot`,TTL)。
- `ai.py` — 抽出 `validate_node`/`slugify_id`;删 `list_models` 死代码。

**后端(路由/集成):**
- `main.py` — `AgentChatReq.history`;接 graph 快照缓存;`/api/ai/apply-node`、`/api/ai/apply-tasks`;wiki space 配置(`/api/lark/spaces`、`/api/lark/config`)。
- `larkpub.py` — `publish_doc(xml, title, wiki_space_id)` 支持 wiki 归档;URL 正则匹配 `/docx/` 和 `/wiki/`。

**测试:**
- `tests/test_tool_runtime.py`、`tests/test_loop.py`、`tests/test_prompts.py`、`tests/test_session.py`、`tests/test_larkpub.py` — 各自更新/新增。

**前端:**
- `src/api.ts` — `agentChatStream(text, history, cb)`;`applyNode`、`applyTasks`、`listWikiSpaces`、`setWikiSpace`。
- `src/AgentChat.tsx` — `send` 带 history;消费 `node_proposal`。
- `src/NodeProposalCard.tsx` — 新组件:应用/编辑/丢弃。
- `src/DocCard.tsx` — 显示 doc_type + wiki/docx 标识。
- `src/types.ts` — `node_proposal` 字段细化;apply 请求/响应类型。
- `src/panels/SetupPanel.tsx` — wiki space 选择器。

---

## 执行顺序总览

- Phase 1 — 数据结构地基(必先做,后续都依赖):Task 1(execute_tool 返回值)、Task 2(parse_react 正则化)
- Phase 2 — 记忆:Task 3(graph 快照缓存)、Task 4(history 注入)
- Phase 3 — Prompt 工程(被短路/提案依赖):Task 5
- Phase 4 — Planner 短路:Task 6
- Phase 5 — 提案闭环:Task 7(node 校验器)、Task 8(add_node/add_tasks 产事件)、Task 9(apply 端点)、Task 10(前端卡片)
- Phase 6 — Reflexion:Task 11
- Phase 7 — doc→wiki:Task 12(larkpub wiki)、Task 13(wiki 配置端点)、Task 14(Writer 差异化 + 前端)
- Phase 8 — 收尾:Task 15(端到端冒烟 + 文档)

---

## Phase 1 — 数据结构地基

### Task 1: `execute_tool` 返回值升级为 `ToolResult`(text + events)

**Why first:** spec §4.1 的核心改动,所有后续工具增强(提案事件)都建立在「工具能产事件」上。先做这步,让契约稳定。

**Files:**
- Modify: `skill-tree/backend/agent/tool_runtime.py`
- Modify: `skill-tree/backend/agent/loop.py:155-161`
- Modify: `skill-tree/backend/tests/test_tool_runtime.py`(全部 7 处调用)

- [ ] **Step 1: 写失败测试 — execute_tool 返回 dict 含 text + events**

在 `tests/test_tool_runtime.py` 顶部加 import,再新增测试:

```python
from agent.tool_runtime import Context, execute_tool, ToolError, ToolResult


def test_execute_tool_returns_tool_result_dict():
    """execute_tool 返回 {text, events},events 默认空 list。"""
    graph = {"nodes": [{"id": "deepfm", "name": "DeepFM", "state": "learning", "pct": 50,
                        "mastered": 2, "total_points": 4}],
             "overview": {"overall_pct": 45}}
    out = execute_tool("get_progress", {}, _ctx(graph=graph))
    assert isinstance(out, dict)
    assert "text" in out and "45" in out["text"]
    assert out.get("events") == []
```

- [ ] **Step 2: 运行确认失败**

Run: `cd skill-tree/backend && python -m pytest tests/test_tool_runtime.py::test_execute_tool_returns_tool_result_dict -v`
Expected: FAIL — `out` 是 str,`isinstance(out, dict)` 为 False。

- [ ] **Step 3: 实现 — 定义 ToolResult + 改写所有工具返回值**

在 `agent/tool_runtime.py` 顶部(`ToolError` 之后)加:

```python
class ToolResult(dict):
    """工具执行结果。text=给模型看的文本;events=要 emit 的 SSE 事件(list[dict])。
    透传 dict 用法({}.get/.update),同时方便 isinstance 判断。"""
    pass


def _ok(text: str, events: list | None = None) -> ToolResult:
    return ToolResult(text=text, events=events or [])
```

把每个工具函数的返回值从 `return "..."` 改为 `return _ok("...")`。逐个改(共 8 个函数):

- `_get_progress`:`return _ok(" ".join(parts))`
- `_get_node`:`return _ok(f"节点 {n.get('name')}...")`(成功分支)和 `return _ok(f"未找到节点 {nid}。")`
- `_get_next`:`return _ok(f"...")`(两个分支)
- `_get_direction`:`return _ok("\n".join(lines))` 和 `return _ok(f"未找到方向 {did}。")`
- `_search_knowledge`:`return _ok("（知识库未就绪...)")` / `return _ok("未检索到...")` / `return _ok("\n".join(...))`
- `_add_node`:`return _ok(f"[建议·待确认] ...")`(Task 8 会重写,先保持文本)
- `_add_tasks`:`return _ok(f"[建议·待确认] ...")`
- `_toggle_task`:`return _ok("已更新。" if ok else "更新失败：未找到该任务。")` 和 `return _ok("（当前上下文不支持直接勾选）")`

- [ ] **Step 4: 改 loop.py 的调用点**

`agent/loop.py:155-161`,把:

```python
        try:
            observation = execute_tool(action, args, ctx)
        except Exception as e:
            observation = f"工具执行出错: {e}"
        yield {"type": "tool_result", "action": action, "content": observation}
```

改为:

```python
        try:
            tresult = execute_tool(action, args, ctx)
            observation = tresult.get("text", "")
            for ev in tresult.get("events", []):
                yield ev
        except Exception as e:
            observation = f"工具执行出错: {e}"
        yield {"type": "tool_result", "action": action, "content": observation}
```

- [ ] **Step 5: 更新 test_tool_runtime.py 既有测试(7 处 str→dict)**

所有 `out = execute_tool(...)` 后的断言,把 `out` 改为 `out["text"]`。示例:

```python
def test_get_progress_from_graph():
    ...
    out = execute_tool("get_progress", {}, _ctx(graph=graph))
    assert "45" in out["text"]
    assert "deepfm" in out["text"] or "DeepFM" in out["text"]
```

对 `test_get_node_missing_returns_hint`、`test_add_node_returns_proposal_not_written`、`test_get_direction_returns_nodes_and_next`、`test_get_direction_unknown_returns_hint` 同样改:`assert X in out["text"]`。

- [ ] **Step 6: 运行全部测试确认通过**

Run: `cd skill-tree/backend && python -m pytest tests/test_tool_runtime.py tests/test_loop.py -v`
Expected: PASS(test_loop 里没直接断言 observation 类型,应不受影响,但跑一遍确认)。

- [ ] **Step 7: 提交**

```bash
cd "D:\Projects\Resume"
git add skill-tree/backend/agent/tool_runtime.py skill-tree/backend/agent/loop.py skill-tree/backend/tests/test_tool_runtime.py
git commit -m "refactor(agent): execute_tool 返回 ToolResult(text+events)

工具执行结果从 str 升级为 {text, events},为后续 node_proposal 事件铺垫。
loop.py 转发 events 给 SSE。"
```

---

### Task 2: `parse_react` 正则化(容错中文注释/换行/多行 JSON)

**Why:** spec §6.2 + §0.2 隐患 #1。现有 `split()[0]` 在 `Action: get_progress（查进度）` 下断成 `get_progress（查进度）`。短路/提案上线后调用更频繁,先修稳。

**Files:**
- Modify: `skill-tree/backend/agent/loop.py:39-57`(`parse_react` + `_after`)
- Modify: `skill-tree/backend/tests/test_loop.py`

- [ ] **Step 1: 写失败测试 — 边界用例集合**

在 `tests/test_loop.py` 的 `parse_react` 测试区追加:

```python
def test_parse_react_action_with_chinese_comment():
    """Action 后跟中文括号注释,应只取工具名。"""
    step = parse_react("Thought: 查\nAction: get_progress（查进度）\nArguments: {}")
    assert step["type"] == "tool"
    assert step["action"] == "get_progress"


def test_parse_react_action_on_next_line():
    """Action 与工具名之间换行。"""
    step = parse_react("Thought: 查\nAction:\nget_progress\nArguments: {}")
    assert step["action"] == "get_progress"


def test_parse_react_multiline_json_arguments():
    """Arguments 是多行 JSON。"""
    text = ('Thought: x\nAction: add_node\nArguments: {\n  "description": "LightGCN"\n}')
    step = parse_react(text)
    assert step["type"] == "tool"
    assert step["arguments"] == {"description": "LightGCN"}


def test_parse_react_final_answer_multiline():
    """Final Answer 后是多行内容。"""
    step = parse_react("Thought: ok\nFinal Answer: 第一行\n第二行")
    assert step["type"] == "final"
    assert "第一行" in step["answer"] and "第二行" in step["answer"]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd skill-tree/backend && python -m pytest tests/test_loop.py -k "chinese_comment or next_line or multiline_json or multiline" -v`
Expected: 4 个 FAIL(action 提取错 / arguments 解析失败)。

- [ ] **Step 3: 重写 parse_react 用正则**

把 `agent/loop.py` 的 `parse_react` 和 `_after` 函数整体替换为:

```python
def parse_react(text: str) -> dict:
    """解析 ReAct 一步。返回 {type: tool|final, action?, arguments?, answer?}。
    正则化容错:Action 后中文注释/括号、Action 换行、多行 JSON Arguments。
    都不匹配→当 final(原样 answer,优雅降级)。"""
    # 工具步:Action 行
    m_action = re.search(r"Action\s*:\s*([A-Za-z_]\w*)", text)
    if m_action:
        action = m_action.group(1)
        # Arguments:从 Action 之后(或 Arguments: 标记后)到 EOF/下一标记
        m_args = re.search(r"Arguments\s*:\s*([\s\S]*?)(?=\n(?:Thought|Action|Final Answer)\s*:|$)", text)
        args: dict = {}
        if m_args:
            raw = m_args.group(1).strip()
            if raw:
                try:
                    parsed = json.loads(raw)
                    args = parsed if isinstance(parsed, dict) else {}
                except Exception:
                    args = {}
        return {"type": "tool", "action": action, "arguments": args}
    # Final Answer
    m_final = re.search(r"Final Answer\s*:\s*([\s\S]*)", text)
    if m_final:
        return {"type": "final", "answer": m_final.group(1).strip()}
    # 都没有→当 final(原样)
    return {"type": "final", "answer": text.strip()}
```

删除现在不再使用的 `_after` 函数(确认全文无其它引用:`grep -n "_after" agent/loop.py` 应只剩定义行)。

- [ ] **Step 4: 运行全部 loop 测试确认通过**

Run: `cd skill-tree/backend && python -m pytest tests/test_loop.py -v`
Expected: PASS(含原有 3 个 parse_react 测试 + 4 个新边界)。

- [ ] **Step 5: 提交**

```bash
cd "D:\Projects\Resume"
git add skill-tree/backend/agent/loop.py skill-tree/backend/tests/test_loop.py
git commit -m "fix(agent): parse_react 正则化,容错中文注释/换行/多行JSON

替换 split()[0] 脆弱提取;补 4 个边界用例。"
```

---

## Phase 2 — 记忆

### Task 3: SessionStore 改做 graph 快照缓存

**Why:** spec §2.3。SessionStore 原本设计当记忆载体但从未被调用,且 §2.1 决定记忆改由前端发。给 SessionStore 一个真实有用的职责:缓存 graph 快照,避免每条消息重算 layout/progress。

**Files:**
- Modify: `skill-tree/backend/agent/session.py`
- Modify: `skill-tree/backend/tests/test_session.py`
- Modify: `skill-tree/backend/main.py`(`_build_ctx` 接缓存)

- [ ] **Step 1: 写失败测试 — 快照存取 + TTL 失效**

在 `tests/test_session.py` 末尾追加:

```python
def test_snapshot_store_and_get():
    store = SessionStore(ttl=60)
    store.set_snapshot("u1", {"overview": {"overall_pct": 50}})
    snap = store.get_snapshot("u1")
    assert snap == {"overview": {"overall_pct": 50}}


def test_snapshot_miss_returns_none():
    store = SessionStore(ttl=60)
    assert store.get_snapshot("nope") is None


def test_snapshot_invalidates_after_ttl():
    store = SessionStore(ttl=0)
    store.set_snapshot("u1", {"x": 1})
    time.sleep(0.01)
    assert store.get_snapshot("u1") is None


def test_snapshot_invalidate_manual():
    store = SessionStore(ttl=60)
    store.set_snapshot("u1", {"x": 1})
    store.invalidate_snapshot("u1")
    assert store.get_snapshot("u1") is None
```

- [ ] **Step 2: 运行确认失败**

Run: `cd skill-tree/backend && python -m pytest tests/test_session.py -k snapshot -v`
Expected: FAIL — `set_snapshot`/`get_snapshot` 不存在(AttributeError)。

- [ ] **Step 3: 实现 — 给 Session 加 snapshots 字典 + SessionStore 方法**

`agent/session.py` 顶部 import 加 `Any`:
```python
from typing import Any
```

`Session` dataclass 增字段:
```python
@dataclass
class Session:
    uid: str
    messages: list[dict] = field(default_factory=list)      # 保留(兼容/未来用)
    graph_snapshot: dict | None = None                      # 复用:graph 快照
    snapshots: dict = field(default_factory=dict)           # 新:通用快照桶 key→value
    last_active: float = field(default_factory=time.time)
```

`SessionStore` 增三个方法(放在 `clear` 之后):

```python
    def set_snapshot(self, uid: str, key: str, value: Any) -> None:
        s = self.get_or_create(uid)        # 自动刷新 last_active
        s.snapshots[key] = value

    def get_snapshot(self, uid: str, key: str) -> Any | None:
        s = self._sessions.get(uid)
        if s is None or (time.time() - s.last_active) > self.ttl:
            return None
        return s.snapshots.get(key)

    def invalidate_snapshot(self, uid: str, key: str) -> None:
        s = self._sessions.get(uid)
        if s is not None:
            s.snapshots.pop(key, None)
```

> 注意:签名是 `set_snapshot(uid, key, value)`(带 key,通用)。上面的测试用 `store.set_snapshot("u1", {...})` 是两参——**改成三参**。修正测试:
> ```python
> store.set_snapshot("u1", "graph", {"overview": {"overall_pct": 50}})
> snap = store.get_snapshot("u1", "graph")
> ```
> `test_snapshot_invalidates_after_ttl` 和 `invalidate_manual` 同理加 `"graph"` 作为第二参。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd skill-tree/backend && python -m pytest tests/test_session.py -v`
Expected: PASS(含原有 4 个 + 新 4 个)。

- [ ] **Step 5: main.py 接缓存 — `_build_ctx` 先查快照**

`main.py` 顶部已有 `SESSIONS = agent_session.SessionStore(ttl=1800)`。把 `_build_ctx` 的计算逻辑包一层缓存。先 Read 确认 `_build_ctx` 当前代码(main.py:401-443),然后在函数开头加:

```python
def _build_ctx(uid: str) -> tuple[agent_tool.Context, dict]:
    """组装工具执行上下文:当前图谱(layout+掌握度) + 简历 + retriever + 勾选回调。"""
    dd = user_dir(uid)
    cached = SESSIONS.get_snapshot(uid, "graph")
    if cached is not None:
        # 复用缓存的 graph,但仍重建 ctx(回调依赖闭包)
        graph, trees = cached["graph"], cached["trees"]
    else:
        trees = load_trees(dd)
        lay = layout_mod.compute_layout(trees)
        raw_nodes: dict[str, dict] = {}
        for t in trees:
            for b in t.get("branches", []):
                for n in b.get("nodes", []):
                    raw_nodes.setdefault(n["id"], n)
        for n in lay["nodes"]:
            raw = raw_nodes.get(n["id"], {})
            m, tot, pct = progress_mod.node_mastery(raw)
            n["mastered"], n["total_points"], n["pct"] = m, tot, pct
            n["state"] = progress_mod.node_status(raw)
        ov = {"overall_pct": 0, "mastered_points": 0, "total_points": 0}
        for t in trees:
            mm, tt, _ = progress_mod.tree_progress(t.get("branches", []))
            ov["mastered_points"] += mm
            ov["total_points"] += tt
        ov["overall_pct"] = 0 if ov["total_points"] == 0 else round(ov["mastered_points"] / ov["total_points"] * 100)
        graph = {"nodes": lay["nodes"], "overview": ov}
        SESSIONS.set_snapshot(uid, "graph", {"graph": graph, "trees": trees})
    resume: dict = {}
    prof_p = dd / "profile.json"
    if prof_p.exists():
        resume = _load_json(prof_p)
    cfg = _load_json(llm_config_path(uid)) if llm_config_path(uid).exists() else {}
    retriever = Retriever(index_dir=rag_index_dir(uid), cfg=cfg)
    # ... 剩余 on_toggle / Context 构造不变
```

> **重要:`patch_task` 必须失效缓存**——用户勾选任务后图谱变了。在 `main.py` 的 `patch_task`(main.py:211-222)`_save_json(path, full)` 之后、`return get_graph(...)` 之前加一行:
> ```python
    SESSIONS.invalidate_snapshot(uid, "graph")
```
> 同理 `apply-tree`、`apply-direction`(Task 9 新增的 apply-node/apply-tasks 也要加)。

- [ ] **Step 6: 运行全部测试 + 手动确认**

Run: `cd skill-tree/backend && python -m pytest tests/ -q`
Expected: PASS(全 78+)。

- [ ] **Step 7: 提交**

```bash
cd "D:\Projects\Resume"
git add skill-tree/backend/agent/session.py skill-tree/backend/tests/test_session.py skill-tree/backend/main.py
git commit -m "feat(agent): SessionStore 改做 graph 快照缓存(TTL)

记忆改由前端发历史(见 Task 4),SessionStore 改为缓存 graph 快照避免每条消息
重算 layout/progress。patch_task 等写操作失效缓存。"
```

---

### Task 4: 前端发 history + 后端 history 注入

**Why:** spec §2.2、§2.4。记忆的核心:前端把最近 6 轮 user+answer 随请求发出,后端注入 Executor。

**Files:**
- Modify: `skill-tree/backend/main.py`(`AgentChatReq` + `agent_chat`)
- Modify: `skill-tree/backend/agent/loop.py`(`run_agent` 增 history 参数)
- Modify: `skill-tree/backend/tests/test_loop.py`
- Modify: `skill-tree/frontend/src/api.ts`、`src/AgentChat.tsx`

- [ ] **Step 1: 写失败测试 — history 被注入 messages**

在 `tests/test_loop.py` 末尾追加:

```python
def test_loop_history_is_injected_into_messages():
    """前端发来的 history 应前置注入 Executor 的 messages。"""
    fake = FakeChat([
        {"content": '{"intent":"query","sub_tasks":[],"needs_doc":false}', "tool_calls": []},
        {"content": "Thought: 够\nFinal Answer: 你上次问的是 DCN。", "tool_calls": []},
    ])
    ctx = _ctx()
    history = [{"role": "user", "content": "DeepFM 学完了"},
               {"role": "assistant", "content": "建议学 DCN"}]
    list(run_agent(ctx, "那 DCN 之后呢", chat_fn=fake, cfg={"base_url": "x", "api_key": "y"},
                   history=history))
    # 第二次调用(Executor)的 messages 应含 history
    executor_call = fake.calls[1]
    roles_content = [(m["role"], m["content"]) for m in executor_call["messages"]]
    assert ("user", "DeepFM 学完了") in roles_content
    assert ("assistant", "建议学 DCN") in roles_content
```

- [ ] **Step 2: 运行确认失败**

Run: `cd skill-tree/backend && python -m pytest tests/test_loop.py::test_loop_history_is_injected_into_messages -v`
Expected: FAIL — `run_agent() got an unexpected keyword argument 'history'`。

- [ ] **Step 3: 实现 — run_agent 增 history 参数**

`agent/loop.py` 的 `run_agent` 签名改为:

```python
def run_agent(ctx: Context, user_input: str, chat_fn=_default_chat,
              cfg: dict | None = None, max_steps: int = 6,
              history: list[dict] | None = None) -> Iterator[dict]:
```

在构造 Executor `messages` 处(原 `messages = [{"role": "system", ...}, {"role": "user", ...}]`),改为把 history 插在 system 和当前 user 之间:

```python
    messages = [{"role": "system", "content": sys_e}]
    for m in (history or []):
        # 只保留 role/content,丢掉 events 等前端字段;限最近 12 条
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_input})
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd skill-tree/backend && python -m pytest tests/test_loop.py -v`
Expected: PASS。

- [ ] **Step 5: 后端 main.py — AgentChatReq + agent_chat 透传 history**

`main.py` 的 `AgentChatReq`:

```python
class AgentChatReq(BaseModel):
    message: str
    history: list = []        # 最近 N 轮 user/assistant 文本(前端发来)
```

`agent_chat` 的 `event_stream`:

```python
    def event_stream():
        for ev in agent_loop.run_agent(ctx, req.message, cfg=cfg, history=req.history):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
```

- [ ] **Step 6: 前端 api.ts — agentChatStream 带 history**

先 Read `src/api.ts` 找到 `agentChatStream` 定义。改为:

```typescript
export async function agentChatStream(
  text: string,
  history: { role: 'user' | 'assistant'; content: string }[],
  cb: (ev: AgentEvent) => void,
): Promise<void> {
  // ... 已有 fetch/SSE 逻辑,body 里加 history
  const res = await fetch(`${API}/agent/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-User-Id': getUserId() },
    body: JSON.stringify({ message: text, history }),
  })
  // ... 已有 SSE 解析逻辑不变
}
```

(保留原有 SSE 读取循环,只改 body 加 `history` 字段。)

- [ ] **Step 7: 前端 AgentChat.tsx — send 构造 history**

`AgentChat.tsx` 的 `send`(约 line 100)调用处改为:

```typescript
      const history = (current?.messages ?? [])
        .slice(-12)
        .filter(m => m.content)              // 丢掉空内容
        .map(m => ({ role: m.role, content: m.content }))
      await api.agentChatStream(text, history, (ev: AgentEvent) => {
```

- [ ] **Step 8: 前端构建确认**

Run: `cd skill-tree/frontend && npm run build`
Expected: 构建成功(无 TS 报错)。

- [ ] **Step 9: 提交**

```bash
cd "D:\Projects\Resume"
git add skill-tree/backend/main.py skill-tree/backend/agent/loop.py skill-tree/backend/tests/test_loop.py skill-tree/frontend/src/api.ts skill-tree/frontend/src/AgentChat.tsx
git commit -m "feat(agent): 前端发 history + 后端注入(多轮记忆)

记忆由客户端按上下文窗口裁剪(最近 12 条)后随请求发出,服务端无状态注入 Executor。
解耦 UI 会话与 agent 记忆。"
```

---

## Phase 3 — Prompt 工程(被后续依赖)

### Task 5: 三套 prompt 加 few-shot + 新增 SYS_CHAT_DIRECT / SYS_REFLECT

**Why:** spec §6.1。few-shot 示例要先于短路(Task 6 用 SYS_CHAT_DIRECT)、Reflexion(Task 11 用 SYS_REFLECT)。且 §5.4 约定 Final Answer 须完整可交付,靠 Executor few-shot 训练。

**Files:**
- Modify: `skill-tree/backend/agent/prompts.py`
- Modify: `skill-tree/backend/tests/test_prompts.py`

- [ ] **Step 1: 写失败测试 — few-shot 存在 + 新模板存在**

在 `tests/test_prompts.py` 末尾追加:

```python
from agent.prompts import SYS_CHAT_DIRECT, SYS_REFLECT, render_chat_direct, render_reflect


def test_executor_has_few_shot_examples():
    """Executor prompt 含 ReAct 示例(示例/Example 标记)。"""
    assert "示例" in SYS_EXECUTOR or "Example" in SYS_EXECUTOR or "例子" in SYS_EXECUTOR


def test_planner_has_few_shot_examples():
    assert "示例" in SYS_PLANNER or "Example" in SYS_PLANNER


def test_chat_direct_template_exists():
    assert "直接回答" in SYS_CHAT_DIRECT or "直接给" in SYS_CHAT_DIRECT


def test_reflect_template_outputs_json():
    assert '"ok"' in SYS_REFLECT and '"gap"' in SYS_REFLECT


def test_render_chat_direct_injects():
    p = render_chat_direct(history_summary="之前聊了 DCN")
    assert "DCN" in p


def test_render_reflect_injects():
    p = render_reflect(question="下一步学啥", observations="整体45%",
                       draft="建议学 DCN")
    assert "下一步学啥" in p
    assert "DCN" in p
```

- [ ] **Step 2: 运行确认失败**

Run: `cd skill-tree/backend && python -m pytest tests/test_prompts.py -v`
Expected: FAIL — import `SYS_CHAT_DIRECT`/`SYS_REFLECT` 报错 + few-shot 断言失败。

- [ ] **Step 3: 实现 prompts.py — 给三套加 few-shot + 新增两套**

**3a. Planner 加 few-shot**(在 `输出:` 行之前插入示例段):

```python
SYS_PLANNER = """你是技能树系统的任务规划器。判断用户意图，输出 JSON 分类。
只输出一个 JSON 对象，不要多余文字。

意图类别：
- "chat": 闲聊/问候/泛泛提问（如"你好""学算法有啥用"）
- "query": 查询当前状态/知识（如"我学到哪了""DeepFM是什么"）
- "mutate": 修改技能树（如"加个 LightGCN 节点""标记这个学完了"）
- "produce": 产出文档/笔记/复习卡（如"整理个笔记""生成复习卡""本周周报"）

示例：
- "你好" → {"intent":"chat","sub_tasks":[],"needs_doc":false}
- "我整体进度怎么样" → {"intent":"query","sub_tasks":[],"needs_doc":false}
- "加个 xDeepFM 节点" → {"intent":"mutate","sub_tasks":["生成 xDeepFM 节点"],"needs_doc":false}
- "帮我整理个 DeepFM 的学习笔记" → {"intent":"produce","sub_tasks":["整理 DeepFM 笔记"],"needs_doc":true}

用户当前进度摘要：{progress_summary}

用户输入：{user_input}
输出：{{"intent": "...", "sub_tasks": ["可选子任务"], "needs_doc": bool}}"""
```

**3b. Executor 加 few-shot + 工具选择指引**(替换整个 `SYS_EXECUTOR`):

```python
SYS_EXECUTOR = """你是技能树系统的学习助手。用工具回答用户问题。
遵循 ReAct：先 Thought（思考该用哪个工具），再 Action（调工具），看到 Observation 后继续，直到能 Final Answer。

可用工具：
{tools}

当前用户技能树状态：
{graph_summary}

工具选择指引：
- 问"学到哪了/进度"：若上面的状态摘要已够，直接 Final Answer；否则调 get_progress。
- 问某客观知识（如"DeepFM 是什么""DCN 原理"）：优先 search_knowledge，不要凭空编造。引用用 [1][2]。
- 问"下一步学啥"：调 get_next 或 get_direction。
- 要加节点/补任务：调 add_node/add_tasks（只生成建议，由用户确认）。

规则：
1. 改图谱的工具（add_node/add_tasks）只生成建议，最终由用户确认。
2. 最多思考 6 步，信息够了就 Final Answer，不要过度调用。
3. Final Answer 用中文，带必要的 [引用]，可含 markdown（标题/列表/代码块/加粗）。

示例（客观知识→检索）：
Thought: 这是客观知识问题，需要检索。
Action: search_knowledge
Arguments: {{"query": "DeepFM 特征交叉"}}
（Observation: [1] DeepFM 由 FM+DNN 组成...）
Thought: 够了。
Final Answer: ## DeepFM\nDeepFM 由 **FM 部分**和 **DNN 部分**组成，并联输出 [1]。\n- FM：显式二阶特征交叉\n- DNN：隐式高阶交叉

示例（状态查询→直接答）：
Thought: 状态摘要已写明整体 45%，够了。
Final Answer: 你整体掌握度 45%，DeepFM 进行中（50%）。建议先吃透 DeepFM 再推进。

输出格式（严格，每步三行或最终两行）：
Thought: <思考>
Action: <工具名>
Arguments: <JSON 对象>
--- 或 ---
Thought: <思考>
Final Answer: <给用户的最终回答>"""
```

> 注意 few-shot 的 Final Answer 是**完整可交付 markdown**(呼应 §5.4:它会被原样 chunk 输出,不再二次润色)。

**3c. 新增 SYS_CHAT_DIRECT + SYS_REFLECT**(文件末尾,`render_*` 之前):

```python
SYS_CHAT_DIRECT = """你是技能树系统的学习助手。请直接回答用户，不要使用 ReAct 格式（不要写 Thought/Action/Final Answer）。
用中文，可用 markdown。若用户引用了学习内容，结合它作答。

近期对话（供上下文）：
{history_summary}"""


SYS_REFLECT = """你是答案校验器。判断 draft_answer 是否真的回答了 user_question，且与 observations 一致（无编造、无遗漏关键点）。
只输出一个 JSON 对象，不要多余文字：
{{"ok": true或false, "gap": "若不 ok，简述缺什么/错什么；ok 则空串"}}

用户问题：{question}
已知信息（来自检索/图谱）：
{observations}
草稿答案：
{draft}
输出：JSON"""
```

**3d. 新增 render 函数**(文件末尾):

```python
def render_chat_direct(history_summary: str = "") -> str:
    return SYS_CHAT_DIRECT.format(history_summary=history_summary or "（无）")


def render_reflect(question: str, observations: str, draft: str) -> str:
    return SYS_REFLECT.format(question=question, observations=observations or "（无）", draft=draft)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd skill-tree/backend && python -m pytest tests/test_prompts.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
cd "D:\Projects\Resume"
git add skill-tree/backend/agent/prompts.py skill-tree/backend/tests/test_prompts.py
git commit -m "feat(prompt): 三套加 few-shot + 新增 SYS_CHAT_DIRECT/SYS_REFLECT

Executor few-shot 训练模型输出完整可交付 Final Answer(呼应统一流式口径)。
Planner 4 例固化分类。chat 直答模板 + Reflect JSON 校验模板。"
```

---

## Phase 4 — Planner 短路

### Task 6: chat 意图短路直答 + 移除 _stream_final,统一流式口径

**Why:** spec §3.2 + §5.4。chat 一步直答;同时把所有路径的「最终输出」统一为「拿全文本→chunk 成 delta」,删掉 `_stream_final`(二次调模型 + 前缀剥离状态机)。

**Files:**
- Modify: `skill-tree/backend/agent/loop.py`
- Modify: `skill-tree/backend/tests/test_loop.py`

- [ ] **Step 1: 写失败测试 — chat 短路只 1 次 Executor 调用、无工具**

在 `tests/test_loop.py` 追加:

```python
def test_loop_chat_short_circuit_no_react():
    """chat intent → 单步直答,不进 ReAct(无 tool_call 事件)。"""
    fake = FakeChat([
        {"content": '{"intent":"chat","sub_tasks":[],"needs_doc":false}', "tool_calls": []},
        {"content": "你好！学算法能锻炼思维。", "tool_calls": []},   # chat 直答(非流式,会被 chunk)
    ])
    ctx = _ctx()
    events = list(run_agent(ctx, "你好", chat_fn=fake, cfg={"base_url": "x", "api_key": "y"}))
    types = [e["type"] for e in events]
    assert "thinking" in types
    assert "delta" in types and "final_done" in types
    assert not any(e["type"] == "tool_call" for e in events)   # 无工具
    full = "".join(e["content"] for e in events if e["type"] == "delta")
    assert "学算法" in full
    # Executor 只被调 1 次(Planner 1 次 + chat 直答 1 次 = 共 2 次)
    assert len(fake.calls) == 2
```

- [ ] **Step 2: 运行确认失败**

Run: `cd skill-tree/backend && python -m pytest tests/test_loop.py::test_loop_chat_short_circuit_no_react -v`
Expected: FAIL — 当前 chat 也走 ReAct + `_stream_final`(会要第 3 条响应,FakeChat 给的会错位)。

- [ ] **Step 3: 实现 — run_agent 加 chat 短路分支**

在 `agent/loop.py` 的 `run_agent` 里,Planner 之后、Executor 循环之前,插入 chat 短路。先 Read 当前 `run_agent` 结构(loop.py:77-174),然后:

在 `yield {"type": "thinking", "content": f"意图：{intent.get('intent', 'query')}"}` 之后插入:

```python
    # ── 2a. chat 短路:单步直答,不进 ReAct ──
    if intent.get("intent") == "chat":
        yield from _chat_direct(ctx, user_input, history or [], chat_fn, cfg)
        yield {"type": "done"}
        return
```

在文件中(`_run_writer` 附近)新增 `_chat_direct`:

```python
def _chat_direct(ctx, user_input, history, chat_fn, cfg) -> Iterator[dict]:
    """chat 意图:一次 LLM 直答,拿全文本后 chunk 成 delta(统一流式口径)。"""
    sys_c = render_chat_direct(_history_summary(history))
    messages = [{"role": "system", "content": sys_c}]
    for m in history:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_input})
    try:
        res = chat_fn(cfg, messages, tools=None)
        answer = res.get("content", "") or "（无回复）"
    except Exception as e:
        answer = f"（生成失败: {e}）"
    yield from _emit_text_as_delta(answer)
    yield {"type": "final_done"}
```

新增通用 `_emit_text_as_delta`(替代 `_stream_final` 的输出职责):

```python
def _emit_text_as_delta(text: str, chunk_size: int = 8) -> Iterator[dict]:
    """把完整文本 chunk 成 delta 事件(统一流式口径:先拿全文本再分段吐)。"""
    for i in range(0, len(text), chunk_size):
        yield {"type": "delta", "content": text[i:i + chunk_size]}
```

新增 `_history_summary`:

```python
def _history_summary(history: list[dict]) -> str:
    if not history:
        return ""
    lines = []
    for m in history[-6:]:
        role = "用户" if m.get("role") == "user" else "助手"
        lines.append(f"{role}: {m.get('content','')[:80]}")
    return "\n".join(lines)
```

import 顶部加:`from agent.prompts import render_planner, render_executor, render_chat_direct, render_reflect`(render_reflect 给 Task 11 用,先一起 import)。

- [ ] **Step 4: 移除 _stream_final,query/produce 也走 _emit_text_as_delta**

把 `_stream_final` 函数整个删除。改写 Executor 循环里 final 步的产出(loop.py 原 `if step["type"] == "final":` 分支):

```python
        if step["type"] == "final":
            answer = step.get("answer", "")
            if answer and not answer.startswith("（已达到最大"):
                yield from _emit_text_as_delta(answer)
            else:
                yield {"type": "final_answer", "content": answer}
            break
```

(把 `yield from _stream_final(...)` 替换为 `yield from _emit_text_as_delta(answer)`。)

同时删除 `_strip_react_prefix`(已无用)。确认无残留引用:`grep -n "_stream_final\|_strip_react_prefix" agent/loop.py` 应为空。

- [ ] **Step 5: 更新既有 chat 测试(去掉第 3 条 fake 响应)**

`test_loop_chat_intent_short_circuits` 现在 chat 走直答,Executor 只调 1 次,不再需要给 `_stream_final` 的流式响应。改为:

```python
def test_loop_chat_intent_short_circuits():
    """Planner 判 chat → 单步直答，不进 ReAct。"""
    fake = FakeChat([
        {"content": '{"intent":"chat","sub_tasks":[],"needs_doc":false}', "tool_calls": []},
        {"content": "你好！加油学算法！", "tool_calls": []},
    ])
    ctx = _ctx()
    events = list(run_agent(ctx, "你好", chat_fn=fake, cfg={"base_url": "x", "api_key": "y"}))
    types = [e["type"] for e in events]
    full = "".join(e.get("content", "") for e in events if e["type"] == "delta")
    assert "thinking" in types
    assert "delta" in types and "final_done" in types
    assert "加油" in full
    assert "done" in types
```

同理 `test_loop_tool_step_then_final` 去掉第 4 条(给 `_stream_final` 的)响应,只留 3 条。

- [ ] **Step 6: 运行全部 loop 测试确认通过**

Run: `cd skill-tree/backend && python -m pytest tests/test_loop.py -v`
Expected: PASS。

- [ ] **Step 7: 提交**

```bash
cd "D:\Projects\Resume"
git add skill-tree/backend/agent/loop.py skill-tree/backend/tests/test_loop.py
git commit -m "feat(agent): chat 短路直答 + 统一流式口径(删 _stream_final)

chat 意图一步直答不进 ReAct;所有路径统一'拿全文本→chunk 成 delta',
移除二次调模型 + 前缀剥离状态机。省一次调用、消除前缀误判。"
```

---

## Phase 5 — 提案闭环

### Task 7: ai.py 抽出 node 校验器(validate_node + slugify_id)

**Why:** spec §5.1。add_node 产出的 node 要过 schema 校验,失败重写。校验逻辑放在 ai.py(紧邻 _norm_node),被 tool_runtime 复用。顺手删 ai.py:87 死代码(spec §0.2 隐患 #3)。

**Files:**
- Modify: `skill-tree/backend/ai.py`
- Modify: `skill-tree/backend/tests/`(新增 test_ai_validate.py 或并入现有)
- Create: `skill-tree/backend/tests/test_ai_validate.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_ai_validate.py`:

```python
from __future__ import annotations
from ai import validate_node, slugify_id


def test_slugify_id_lowercases_and_replaces():
    assert slugify_id("DeepFM") == "deepfm"
    assert slugify_id("Light GCN!") == "light_gcn"
    assert slugify_id("xDeepFM") == "xdeepfm"


def test_validate_node_ok():
    node = {"id": "deepfm", "name": "DeepFM", "tasks": []}
    ok, errs = validate_node(node)
    assert ok and errs == []


def test_validate_node_missing_name():
    ok, errs = validate_node({"id": "x", "tasks": []})
    assert not ok and any("name" in e for e in errs)


def test_validate_node_missing_id_autofixed():
    """缺 id 时校验失败,提示(由调用方 slugify name 修补)。"""
    ok, errs = validate_node({"name": "DeepFM", "tasks": []})
    assert not ok and any("id" in e for e in errs)


def test_validate_node_tasks_must_be_list():
    ok, errs = validate_node({"id": "x", "name": "X", "tasks": "not list"})
    assert not ok
```

- [ ] **Step 2: 运行确认失败**

Run: `cd skill-tree/backend && python -m pytest tests/test_ai_validate.py -v`
Expected: FAIL — import `validate_node`/`slugify_id` 报错。

- [ ] **Step 3: 实现 — ai.py 加 slugify_id + validate_node,删死代码**

在 `ai.py` 的 `_norm_node` 之后加:

```python
import re as _re


def slugify_id(name: str) -> str:
    """把名字转成合法 node id(小写字母数字下划线)。如 'Light GCN!' → 'light_gcn'。"""
    s = name.strip().lower()
    s = _re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s or "node"


def validate_node(node: dict) -> tuple[bool, list[str]]:
    """轻量校验。返回 (ok, [错误信息])。必填:id(非空)、name(非空)、tasks(list)。"""
    errs = []
    if not isinstance(node, dict):
        return False, ["node 不是对象"]
    if not str(node.get("id", "")).strip():
        errs.append("缺少 id")
    if not str(node.get("name", "")).strip():
        errs.append("缺少 name")
    if not isinstance(node.get("tasks", None), list):
        errs.append("tasks 必须是列表")
    return (len(errs) == 0), errs
```

> 注意 `ai.py` 顶部已 `import re`,这里用别名 `_re` 避免与可能的局部冲突;其实可直接复用顶部 re。实现时若顶部已有 `import re`,就用 `re` 不用 `_re`。先 `grep -n "^import re" ai.py` 确认——已有则直接用 `re`。

删 `list_models` 里的死代码(ai.py:87-88):

```python
    except Exception as e:
        return False, str(e)
```
这行(第二个 except)删掉。`list_models` 已有自己的 except 块。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd skill-tree/backend && python -m pytest tests/test_ai_validate.py tests/test_loop.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
cd "D:\Projects\Resume"
git add skill-tree/backend/ai.py skill-tree/backend/tests/test_ai_validate.py
git commit -m "feat(ai): 抽出 validate_node + slugify_id,删 list_models 死代码

为 add_node 提案的 schema 校验铺垫;顺手清理 ai.py:87 重复 except。"
```

---

### Task 8: add_node / add_tasks 产 node_proposal 事件 + 校验重写

**Why:** spec §4.2、§5.1。这是提案闭环的核心:add_node 内部调 ai.generate_node 生成结构化 node,过校验(失败重写),emit node_proposal 事件。Context 需增 cfg 字段。

**Files:**
- Modify: `skill-tree/backend/agent/tool_runtime.py`(`Context` 增 cfg;`_add_node`/`_add_tasks` 重写)
- Modify: `skill-tree/backend/agent/tools.py`(`add_node`/`add_tasks` 描述微调)
- Modify: `skill-tree/backend/main.py`(`_build_ctx` 传 cfg)
- Modify: `skill-tree/backend/tests/test_tool_runtime.py`

- [ ] **Step 1: 写失败测试 — add_node 产 node_proposal 事件**

在 `tests/test_tool_runtime.py` 末尾追加:

```python
def test_add_node_emits_proposal_event():
    """add_node 返回 ToolResult,events 含 node_proposal,node 通过校验。"""
    from tests.fakes import fake_cfg
    # ai.generate_node 会调 LLM;这里 monkeypatch 掉
    import ai
    import agent.tool_runtime as tr

    def fake_gen_node(cfg, description, node_id, existing_ids):
        return {"id": "lightgcn", "name": "LightGCN", "category": "推荐",
                "status": "locked", "depends_on": [], "tasks": [{"id": "t1", "title": "读论文", "done": False}]}
    orig = ai.generate_node
    ai.generate_node = fake_gen_node
    try:
        ctx = _ctx()
        ctx.cfg = fake_cfg()
        out = execute_tool("add_node", {"description": "LightGCN"}, ctx)
    finally:
        ai.generate_node = orig
    assert out["text"]                           # 给模型的文本
    assert any(e.get("type") == "node_proposal" for e in out["events"])
    prop = [e for e in out["events"] if e.get("type") == "node_proposal"][0]
    assert prop["mode"] == "new_node"
    assert prop["node"]["id"] == "lightgcn"
    assert prop["node"]["name"] == "LightGCN"


def test_add_node_invalid_then_rewrite():
    """第一次生成的 node 缺 name(校验失败),用 slugify/修补后重写。"""
    import ai
    calls = {"n": 0}

    def fake_gen(cfg, description, node_id, existing_ids):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"id": "x", "tasks": []}        # 缺 name,校验失败
        return {"id": "x", "name": "X", "tasks": []}  # 第二次合规
    orig = ai.generate_node
    ai.generate_node = fake_gen
    try:
        ctx = _ctx()
        ctx.cfg = {"base_url": "x", "api_key": "y"}
        out = execute_tool("add_node", {"description": "X"}, ctx)
    finally:
        ai.generate_node = orig
    assert calls["n"] == 2                          # 重写了一次
    prop = [e for e in out["events"] if e.get("type") == "node_proposal"][0]
    assert prop["node"]["name"] == "X"


def test_add_tasks_emits_proposal_event():
    import ai
    ai.generate_node = lambda cfg, d, nid, eids: {"id": nid or "n", "name": "N",
                                                  "tasks": [{"id": "t2", "title": "新任务", "done": False}]}
    orig = ai.generate_node
    # 暂存以恢复(上面 lambda 没存 orig,改写)
    try:
        ctx = _ctx()
        ctx.cfg = {"base_url": "x", "api_key": "y"}
        out = execute_tool("add_tasks", {"node_id": "n1", "description": "补手算验收"}, ctx)
    finally:
        pass   # ai.generate_node 在下个测试前会被真实 import 覆盖;为干净,显式恢复
    assert any(e.get("type") == "node_proposal" for e in out["events"])
    prop = [e for e in out["events"] if e.get("type") == "node_proposal"][0]
    assert prop["mode"] == "add_tasks"
    assert prop["node_id"] == "n1"
```

> 注意 test_add_tasks 末尾的 monkeypatch 恢复要写干净。实现时改为 `try/finally` 里 `ai.generate_node = orig`,先 `orig = ai.generate_node` 再赋 lambda。修正该测试的写法:
> ```python
def test_add_tasks_emits_proposal_event():
    import ai
    orig = ai.generate_node
    ai.generate_node = lambda cfg, d, nid, eids: {"id": nid or "n", "name": "N",
                                                  "tasks": [{"id": "t2", "title": "新任务", "done": False}]}
    try:
        ctx = _ctx(); ctx.cfg = {"base_url": "x", "api_key": "y"}
        out = execute_tool("add_tasks", {"node_id": "n1", "description": "补手算验收"}, ctx)
    finally:
        ai.generate_node = orig
    assert any(e.get("type") == "node_proposal" for e in out["events"])
    prop = [e for e in out["events"] if e.get("type") == "node_proposal"][0]
    assert prop["mode"] == "add_tasks"
    assert prop["node_id"] == "n1"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd skill-tree/backend && python -m pytest tests/test_tool_runtime.py -k "emits_proposal or rewrite" -v`
Expected: FAIL — add_node 还返回纯文本 proposal,events 空。

- [ ] **Step 3: 实现 — Context 增 cfg;重写 _add_node / _add_tasks**

`agent/tool_runtime.py` 的 `Context` dataclass 增字段:

```python
@dataclass
class Context:
    uid: str
    graph: dict
    resume: dict | None
    retriever: Any
    rag_index_dir: Any
    trees: list = None
    cfg: dict | None = None          # 新:LLM 配置(add_node/add_tasks 生成节点用)
```

重写 `_add_node`:

```python
def _add_node(args, ctx):
    """生成结构化 node 建议,过 schema 校验(失败 slugify/重写一次),emit node_proposal。"""
    import ai
    cfg = ctx.cfg or {}
    desc = args.get("description", "")
    existing = [n.get("id") for n in (ctx.graph.get("nodes") or [])]
    # 收集所有现有 id 供 depends_on 参考
    node = ai.generate_node(cfg, desc, node_id="", existing_ids=existing)
    node = ai._norm_node(node)
    ok, errs = ai.validate_node(node)
    if not ok:
        # 修补:用 slugify(name) 补 id;若 name 也缺,重写一次
        if "缺少 id" in errs and node.get("name"):
            node["id"] = ai.slugify_id(node["name"])
            ok, errs = ai.validate_node(node)
        if not ok:
            try:
                node2 = ai._norm_node(ai.generate_node(cfg, desc, node_id="", existing_ids=existing))
                ok2, _ = ai.validate_node(node2)
                if ok2:
                    node = node2
            except Exception:
                pass
    event = {"type": "node_proposal", "mode": "new_node", "node": node}
    if not ai.validate_node(node)[0]:
        event["incomplete"] = True
    text = f"已生成新节点《{node.get('name', desc)}》建议（含 {len(node.get('tasks', []))} 个任务），请在卡片上确认。"
    return _ok(text, [event])


def _add_tasks(args, ctx):
    """为指定 node 生成补充 tasks/verify,emit node_proposal(add_tasks 模式)。"""
    import ai
    cfg = ctx.cfg or {}
    nid = args.get("node_id", "")
    desc = args.get("description", "")
    node = ai.generate_node(cfg, desc, node_id=nid, existing_ids=[])
    node = ai._norm_node(node)
    tasks = node.get("tasks", [])
    event = {"type": "node_proposal", "mode": "add_tasks", "node_id": nid, "tasks": tasks}
    text = f"已为节点 {nid} 生成 {len(tasks)} 条补充任务,请在卡片上确认。"
    return _ok(text, [event])
```

`main.py` 的 `_build_ctx` 构造 Context 时传 cfg:

```python
    ctx = agent_tool.Context(uid=uid, graph=graph, resume=resume,
                             retriever=retriever, rag_index_dir=rag_index_dir(uid),
                             trees=trees, cfg=cfg)
```

- [ ] **Step 4: 更新既有 test_add_node_returns_proposal_not_written**

原测试 `assert "建议" in out or "proposal" in out.lower()` 现在 out 是 dict。改为:

```python
def test_add_node_returns_proposal_not_written():
    """add_node 返回 ToolResult,text 含'建议/确认'标记,不写盘。"""
    import ai
    orig = ai.generate_node
    ai.generate_node = lambda cfg, d, nid, e: {"id": "x", "name": "X", "tasks": []}
    try:
        out = execute_tool("add_node", {"description": "LightGCN"}, _ctx())
    finally:
        ai.generate_node = orig
    assert "确认" in out["text"] or "建议" in out["text"]
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd skill-tree/backend && python -m pytest tests/test_tool_runtime.py -v`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
cd "D:\Projects\Resume"
git add skill-tree/backend/agent/tool_runtime.py skill-tree/backend/main.py skill-tree/backend/tests/test_tool_runtime.py
git commit -m "feat(agent): add_node/add_tasks 产 node_proposal 事件 + schema 校验

写操作从返回文字升级为产出结构化 node 提案事件;校验失败 slugify/重写一次。
Context 增 cfg 字段。"
```

---

### Task 9: apply-node / apply-tasks 端点

**Why:** spec §4.4。前端卡片「应用」时调这两个端点把 node/tasks 写入树文件。

**Files:**
- Modify: `skill-tree/backend/main.py`
- Modify: `skill-tree/backend/tests/`(test_main 或新建)

- [ ] **Step 1: 写失败测试(纯函数风格,不用 TestClient)**

> **约束:本仓库测试零新增依赖,不装 httpx,不用 FastAPI TestClient。** 把 apply 逻辑抽成纯函数 `_apply_node_to_tree(tree, node, branch_id)` / `_apply_tasks_to_node(tree, node_id, tasks)`,端点调用它。测试直接调纯函数(用 monkeypatch 的 tmp_path 验证写盘)。

新建 `tests/test_apply.py`:

```python
from __future__ import annotations
import json
from pathlib import Path

import main


def _seed_tree() -> dict:
    """一棵含单节点的树。"""
    return {"tree_id": "agent", "order": 1, "title": "Agent", "icon": "🤖", "color": "#4ade80",
            "branches": [{"id": "b", "name": "B", "nodes": [
                {"id": "deepfm", "name": "DeepFM", "category": "推荐", "status": "learning",
                 "depends_on": [], "tasks": [{"id": "t1", "title": "读论文", "done": False}]}]}]}


def test_apply_node_to_tree_appends():
    tree = _seed_tree()
    node = {"id": "dcn", "name": "DCN", "category": "推荐", "status": "locked",
            "depends_on": ["deepfm"], "tasks": [{"id": "t", "title": "读 DCN 论文", "done": False}]}
    main._apply_node_to_tree(tree, node, branch_id="b")
    ids = [n["id"] for b in tree["branches"] for n in b["nodes"]]
    assert "dcn" in ids


def test_apply_node_dedup_same_id():
    tree = _seed_tree()
    node = {"id": "deepfm", "name": "DeepFM2", "tasks": []}   # 同 id 不重复加
    main._apply_node_to_tree(tree, node, branch_id="b")
    deepfms = [n for b in tree["branches"] for n in b["nodes"] if n["id"] == "deepfm"]
    assert len(deepfms) == 1


def test_apply_tasks_to_node_appends():
    tree = _seed_tree()
    main._apply_tasks_to_node(tree, "deepfm",
                              [{"id": "t2", "title": "手算 FM", "done": False}])
    node = [n for b in tree["branches"] for n in b["nodes"] if n["id"] == "deepfm"][0]
    titles = [t["title"] for t in node["tasks"]]
    assert "手算 FM" in titles


def test_apply_tasks_dedup_same_task_id():
    tree = _seed_tree()
    main._apply_tasks_to_node(tree, "deepfm", [{"id": "t1", "title": "重复", "done": False}])
    node = [n for b in tree["branches"] for n in b["nodes"] if n["id"] == "deepfm"][0]
    assert len([t for t in node["tasks"] if t["id"] == "t1"]) == 1
    assert node["tasks"][0]["title"] == "读论文"   # 原始保留
```

> 端点本身只做「读树→调纯函数→存树→失效缓存」,逻辑薄,靠纯函数测试覆盖即可(与现有 test_store/test_chat_store 的风格一致:测数据变换,不测 HTTP)。

- [ ] **Step 2: 运行确认失败**

Run: `cd skill-tree/backend && python -m pytest tests/test_apply.py -v`
Expected: FAIL — 404(端点不存在)。

- [ ] **Step 3: 实现 — main.py 抽纯函数 + 两个端点**

在 `apply_direction` 之后(main.py 约 393 行后)先加**纯函数**(端点和测试都用):

```python
def _apply_node_to_tree(tree: dict, node: dict, branch_id: str | None = None) -> bool:
    """把 node 插入 tree 的指定 branch(空则第一个 branch)。同 id 去重。返回是否插入。"""
    branches = tree.get("branches", [])
    target = None
    for b in branches:
        if branch_id and b.get("id") == branch_id:
            target = b; break
    if target is None and branches:
        target = branches[0]
    if target is None:
        return False
    if any(n.get("id") == node.get("id") for n in target.get("nodes", [])):
        return False    # 同 id 已存在,不重复加
    target.setdefault("nodes", []).append(node)
    return True


def _apply_tasks_to_node(tree: dict, node_id: str, tasks: list) -> bool:
    """把 tasks 追加到 tree 里 id=node_id 的节点。同 task id 去重。返回是否找到节点。"""
    for b in tree.get("branches", []):
        for n in b.get("nodes", []):
            if n.get("id") == node_id:
                existing = {t.get("id") for t in n.get("tasks", [])}
                for t in tasks:
                    if t.get("id") not in existing:
                        n.setdefault("tasks", []).append(t)
                return True
    return False
```

再加**两个端点**(调用纯函数):

```python
class ApplyNodeReq(BaseModel):
    tree_id: str
    node: dict
    branch_id: str | None = None


@app.post("/api/ai/apply-node")
def apply_node(req: ApplyNodeReq, x_user_id: str | None = Header(default=None)) -> dict:
    """把 node_proposal 确认的节点写入指定 tree 文件。"""
    uid = resolve_user(x_user_id)
    dd = user_dir(uid)
    path = _find_tree_file(dd, req.tree_id)
    if path is None:
        raise HTTPException(404, f"tree not found: {req.tree_id}")
    tree = _load_json(path)
    if not _apply_node_to_tree(tree, req.node, req.branch_id):
        raise HTTPException(400, "插入失败:无 branch 或 id 已存在")
    _save_json(path, tree)
    SESSIONS.invalidate_snapshot(uid, "graph")
    return {"ok": True, "written": True}


class ApplyTasksReq(BaseModel):
    tree_id: str
    node_id: str
    tasks: list


@app.post("/api/ai/apply-tasks")
def apply_tasks(req: ApplyTasksReq, x_user_id: str | None = Header(default=None)) -> dict:
    """把 node_proposal 确认的补充 tasks 追加到指定 node。"""
    uid = resolve_user(x_user_id)
    dd = user_dir(uid)
    path = _find_tree_file(dd, req.tree_id)
    if path is None:
        raise HTTPException(404, f"tree not found: {req.tree_id}")
    tree = _load_json(path)
    if not _apply_tasks_to_node(tree, req.node_id, req.tasks):
        raise HTTPException(404, f"node not found: {req.node_id}")
    _save_json(path, tree)
    SESSIONS.invalidate_snapshot(uid, "graph")
    return {"ok": True}
```

> 注意 `SessionStore.invalidate_snapshot` 签名是 `(uid, key)`,在 Task 3 已定义。`patch_task` 里也已加失效(Task 3 Step 5)。`apply-tree`/`apply-direction` 也补一行 `SESSIONS.invalidate_snapshot(uid, "graph")`(写操作都要失效)。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd skill-tree/backend && python -m pytest tests/test_apply.py -v`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
cd "D:\Projects\Resume"
git add skill-tree/backend/main.py skill-tree/backend/tests/test_apply.py
git commit -m "feat(api): apply-node / apply-tasks 端点(提案确认闭环)

前端 node_proposal 卡片「应用」时把节点/任务写入树文件;写后失效 graph 快照。"
```

---

### Task 10: 前端 node_proposal 卡片 + api

**Why:** spec §8。前端消费 node_proposal 事件,渲染卡片[应用/编辑/丢弃],应用调 Task 9 端点后刷新图谱。

**Files:**
- Modify: `skill-tree/frontend/src/types.ts`
- Modify: `skill-tree/frontend/src/api.ts`
- Create: `skill-tree/frontend/src/NodeProposalCard.tsx`
- Modify: `skill-tree/frontend/src/AgentChat.tsx`

- [ ] **Step 1: types.ts — 细化 node_proposal 事件**

把 `AgentEvent` 里的 `node_proposal` 行改为:

```typescript
  | { type: 'node_proposal'; mode: 'new_node' | 'add_tasks'; node?: NodeSpec; node_id?: string; tasks?: Task[]; incomplete?: boolean }
```

在文件靠上(Task interface 附近)加:

```typescript
export interface NodeSpec {
  id: string
  name: string
  category?: string
  status?: string
  depends_on?: string[]
  tasks: Task[]
}
```

- [ ] **Step 2: api.ts — applyNode / applyTasks**

在 `api.ts` 加:

```typescript
export async function applyNode(treeId: string, node: NodeSpec, branchId?: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${API}/ai/apply-node`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-User-Id': getUserId() },
    body: JSON.stringify({ tree_id: treeId, node, branch_id: branchId }),
  })
  return res.json()
}

export async function applyTasks(treeId: string, nodeId: string, tasks: Task[]): Promise<{ ok: boolean }> {
  const res = await fetch(`${API}/ai/apply-tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-User-Id': getUserId() },
    body: JSON.stringify({ tree_id: treeId, node_id: nodeId, tasks }),
  })
  return res.json()
}
```

(import `NodeSpec`、`Task` from `./types`。`API` 常量、`getUserId` 已存在。)

- [ ] **Step 3: NodeProposalCard.tsx 新组件**

```typescript
import { useState } from 'react'
import type { NodeSpec, Task } from './types'
import { applyNode, applyTasks } from './api'

interface Props {
  mode: 'new_node' | 'add_tasks'
  node?: NodeSpec
  nodeId?: string
  tasks?: Task[]
  incomplete?: boolean
  onApplied?: () => void
  onDiscard?: () => void
}

export function NodeProposalCard({ mode, node, nodeId, tasks, incomplete, onApplied, onDiscard }: Props) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<string>(JSON.stringify(mode === 'new_node' ? node : tasks, null, 2))
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState('')

  const apply = async () => {
    setBusy(true); setMsg('')
    try {
      // tree_id / branch_id 暂用占位:实际从当前图谱上下文取;这里用 prompt 简化
      const treeId = prompt('写入哪个方向(tree_id)?例如 agent / recommendation') || ''
      if (!treeId) { setMsg('已取消'); setBusy(false); return }
      if (mode === 'new_node' && node) {
        const n = editing ? JSON.parse(draft) : node
        await applyNode(treeId, n)
      } else if (mode === 'add_tasks' && nodeId) {
        const ts = editing ? JSON.parse(draft) : tasks
        await applyTasks(treeId, nodeId, ts || [])
      }
      setMsg('✓ 已应用,图谱已更新')
      onApplied?.()
    } catch (e: any) {
      setMsg('✗ ' + String(e.message || e))
    } finally {
      setBusy(false)
    }
  }

  const title = mode === 'new_node' ? `新节点《${node?.name || '?'}》` : `补充任务 → ${nodeId}`
  const count = mode === 'new_node' ? node?.tasks.length ?? 0 : tasks?.length ?? 0

  return (
    <div className="doc-card" style={{ margin: '8px 0', border: '1px solid #38bdf8', borderRadius: 8, padding: 10 }}>
      <div style={{ fontWeight: 600 }}>🆕 {title}</div>
      <div style={{ fontSize: 13, color: '#94a3b8' }}>含 {count} 项{incomplete ? ' · ⚠ 校验不完整,建议编辑' : ''}</div>
      {editing && (
        <textarea value={draft} onChange={e => setDraft(e.target.value)} rows={8}
                  style={{ width: '100%', marginTop: 6, fontFamily: 'monospace', fontSize: 12 }} />
      )}
      <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
        <button onClick={apply} disabled={busy} className="btn-primary">{busy ? '应用中…' : '应用'}</button>
        <button onClick={() => setEditing(v => !v)}>{editing ? '完成编辑' : '编辑'}</button>
        <button onClick={onDiscard}>丢弃</button>
      </div>
      {msg && <div style={{ fontSize: 12, marginTop: 6 }}>{msg}</div>}
    </div>
  )
}
```

- [ ] **Step 4: AgentChat.tsx — 消费 node_proposal**

`AgentChat.tsx` 的消息渲染区(约 line 178-186),在 `DocCard` 渲染旁边加 `NodeProposalCard`:

```typescript
            {current?.messages.map((m, i) => (
              <div key={i}>
                <ChatMessageView msg={m}
                  streaming={streaming && i === (current.messages.length - 1) && m.role === 'assistant'} />
                {m.events?.filter(e => e.type === 'doc_card').map((e, j) => (
                  <DocCard key={`d${j}`} content={(e as any).content || ''} onPublished={() => {}} />
                ))}
                {m.events?.filter(e => e.type === 'node_proposal').map((e, j) => {
                  const ev = e as any
                  return <NodeProposalCard key={`n${j}`} mode={ev.mode} node={ev.node} nodeId={ev.node_id}
                                           tasks={ev.tasks} incomplete={ev.incomplete}
                                           onApplied={() => window.dispatchEvent(new Event('refresh-graph'))}
                                           onDiscard={() => {}} />
                })}
              </div>
            ))}
```

import 顶部加 `import { NodeProposalCard } from './NodeProposalCard'`。

> `refresh-graph` 事件:App.tsx 监听后调 `api.graph()` 刷新。先 Read `App.tsx` 确认有没有现成刷新机制;若有 `refresh()` 函数,直接 props 透传更好。若没有,在 App.tsx 加 `useEffect(() => { const h = () => refresh(); window.addEventListener('refresh-graph', h); return () => window.removeEventListener('refresh-graph', h) }, [])`。实现时按 App.tsx 实际结构调整。

- [ ] **Step 5: 前端构建确认**

Run: `cd skill-tree/frontend && npm run build`
Expected: 构建成功。

- [ ] **Step 6: 提交**

```bash
cd "D:\Projects\Resume"
git add skill-tree/frontend/src/types.ts skill-tree/frontend/src/api.ts skill-tree/frontend/src/NodeProposalCard.tsx skill-tree/frontend/src/AgentChat.tsx
git commit -m "feat(frontend): node_proposal 卡片 + apply api

消费 node_proposal 事件,渲染[应用/编辑/丢弃]卡片;应用调 apply-node/apply-tasks
后刷新图谱。"
```

---

## Phase 6 — Reflexion

### Task 11: Reflexion 答案校验(query/produce,封顶 1 轮)

**Why:** spec §5.2、§5.3、§5.4。ReAct 出 Final Answer 草稿后,Reflect 校验,ok=false 且有步数→注入 gap 续跑(最多 1 轮)。区分度最高的 agent 技巧。

**Files:**
- Modify: `skill-tree/backend/agent/loop.py`
- Modify: `skill-tree/backend/tests/test_loop.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_loop.py` 末尾追加:

```python
def test_loop_reflect_triggers_rerun_on_gap():
    """Reflect 判 ok=false → 注入 gap 续跑一轮,再 Final Answer。"""
    fake = FakeChat([
        {"content": '{"intent":"query","sub_tasks":[],"needs_doc":false}', "tool_calls": []},
        {"content": "Thought: x\nFinal Answer: 建议学 DCN。", "tool_calls": []},   # 草稿
        {"content": '{"ok": false, "gap": "没说为什么推荐 DCN"}', "tool_calls": []},  # Reflect
        {"content": "Thought: 补充\nFinal Answer: 建议 DCN，因为它承接 DeepFM 的特征交叉。", "tool_calls": []},  # 续跑
        {"content": '{"ok": true, "gap": ""}', "tool_calls": []},                   # 二次 Reflect(被 reflect_used 挡掉?不,再 reflect 一次)
    ])
    ctx = _ctx()
    events = list(run_agent(ctx, "下一步学啥,为什么", chat_fn=fake,
                            cfg={"base_url": "x", "api_key": "y"}))
    full = "".join(e.get("content", "") for e in events if e["type"] == "delta")
    assert "特征交叉" in full    # 续跑后的内容


def test_loop_reflect_ok_accepts_draft():
    """Reflect 判 ok=true → 直接接受草稿,不续跑。"""
    fake = FakeChat([
        {"content": '{"intent":"query","sub_tasks":[],"needs_doc":false}', "tool_calls": []},
        {"content": "Thought: x\nFinal Answer: 你整体 45%。", "tool_calls": []},
        {"content": '{"ok": true, "gap": ""}', "tool_calls": []},
    ])
    ctx = _ctx()
    events = list(run_agent(ctx, "进度", chat_fn=fake, cfg={"base_url": "x", "api_key": "y"}))
    full = "".join(e.get("content", "") for e in events if e["type"] == "delta")
    assert "45%" in full


def test_loop_reflect_capped_does_not_loop():
    """Reflect 已用过一次 + 仍不 ok → 接受草稿,不无限续跑。"""
    fake = FakeChat([
        {"content": '{"intent":"query","sub_tasks":[],"needs_doc":false}', "tool_calls": []},
        {"content": "Thought: x\nFinal Answer: 草稿A。", "tool_calls": []},
        {"content": '{"ok": false, "gap": "x"}', "tool_calls": []},
        {"content": "Thought: y\nFinal Answer: 草稿B。", "tool_calls": []},
        {"content": '{"ok": false, "gap": "y"}', "tool_calls": []},  # 二次仍不 ok,但已 reflect 过
    ])
    ctx = _ctx()
    events = list(run_agent(ctx, "x", chat_fn=fake, cfg={"base_url": "x", "api_key": "y"}))
    assert any(e["type"] == "final_done" for e in events)   # 不卡死
    full = "".join(e.get("content", "") for e in events if e["type"] == "delta")
    assert "草稿B" in full    # 接受第二次草稿
```

- [ ] **Step 2: 运行确认失败**

Run: `cd skill-term/backend && python -m pytest tests/test_loop.py -k reflect -v`
Expected: FAIL — 无 Reflect 逻辑,草稿直接输出。

- [ ] **Step 3: 实现 — run_agent 在 final 步插入 Reflect**

在 `agent/loop.py` 的 Executor 循环里,把 final 步分支改为带 Reflect。先 Read 当前 final 分支(Task 6 改过),然后替换为:

```python
        if step["type"] == "final":
            answer = step.get("answer", "")
            if answer and not answer.startswith("（已达到最大"):
                # Reflect(query/produce 才做,且仅 1 轮)
                if intent.get("intent") in ("query", "produce") and not reflect_used:
                    reflect_used, answer = _maybe_reflect_and_rerun(
                        user_input, messages, answer, chat_fn, cfg, reflect_used, locals().get("step_i", 0), max_steps)
                yield from _emit_text_as_delta(answer)
            else:
                yield {"type": "final_answer", "content": answer}
            break
```

> 但续跑需要在循环里继续,不能 break。重构成:Reflect 返回 `(accept: bool, new_answer)`。若 accept=True 直接输出;若 False,把 gap 注入 messages 继续 for 循环。这需要把 Reflect 从「函数返回答案」改成「在循环内控制流」。更清晰的写法:

把 final 分支替换为:

```python
        if step["type"] == "final":
            answer = step.get("answer", "")
            if not answer or answer.startswith("（已达到最大"):
                yield {"type": "final_answer", "content": answer}
                break
            # Reflect(query/produce 才做)
            if intent.get("intent") in ("query", "produce") and not reflect_used:
                reflect_used = True
                ok, gap = _reflect(user_input, messages, answer, chat_fn, cfg)
                if not ok and step_i + 1 < max_steps:
                    # 注入 gap,续跑一轮
                    yield {"type": "thinking", "content": f"自查发现遗漏: {gap}，补充中…"}
                    messages.append({"role": "assistant", "content": answer})
                    messages.append({"role": "user",
                                     "content": f"上面的草稿遗漏: {gap}。请用工具补充后给出更完整的最终回答。"})
                    continue   # 继续循环(下一轮再 final 时 reflect_used 已 True,不再 reflect)
            # 接受答案
            yield from _emit_text_as_delta(answer)
            break
```

在 `run_agent` 循环前初始化:`reflect_used = False`。

新增 `_reflect` 函数(在 `_emit_text_as_delta` 附近):

```python
def _reflect(user_input, messages, draft, chat_fn, cfg) -> tuple[bool, str]:
    """校验草稿是否回答了问题。返回 (ok, gap)。失败回退 ok=True(不阻塞)。"""
    observations = "\n".join(m["content"].replace("Observation:", "").strip()
                             for m in messages
                             if m.get("role") == "user" and "Observation:" in m.get("content", ""))
    sys_r = render_reflect(question=user_input, observations=observations[:800], draft=draft[:800])
    try:
        res = chat_fn(cfg, [{"role": "system", "content": sys_r},
                            {"role": "user", "content": "请输出校验 JSON。"}], tools=None)
        obj = _safe_intent(res.get("content", ""))   # 复用 JSON 解析(容错)
        return bool(obj.get("ok", True)), str(obj.get("gap", ""))
    except Exception:
        return True, ""   # 回退:不阻塞
```

import 顶部已加 `render_reflect`(Task 6 Step 3)。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd skill-tree/backend && python -m pytest tests/test_loop.py -v`
Expected: PASS(含 3 个 reflect 测试 + 原有)。

- [ ] **Step 5: 提交**

```bash
cd "D:\Projects\Resume"
git add skill-tree/backend/agent/loop.py skill-tree/backend/tests/test_loop.py
git commit -m "feat(agent): Reflexion 答案校验(query/produce,封顶1轮)

ReAct 出草稿后 Reflect 校验,ok=false 且有步数→注入 gap 续跑一轮。
失败回退 ok=true 不阻塞。比基础 ReAct 高一阶。"
```

---

## Phase 7 — doc→wiki 沉淀

### Task 12: larkpub 支持 wiki 归档 + URL 正则修正

**Why:** spec §7.3。`publish_doc(xml, title, wiki_space_id)` 优先 wiki +node-create,回退 docx;URL 正则匹配 /docx/ 和 /wiki/。

**Files:**
- Modify: `skill-tree/backend/larkpub.py`
- Modify: `skill-tree/backend/tests/test_larkpub.py`

- [ ] **Step 1: 写失败测试**

先 Read `tests/test_larkpub.py` 了解现有模式,然后追加:

```python
def test_parse_doc_url_matches_wiki_and_docx():
    from larkpub import parse_doc_url
    assert parse_doc_url("see https://a.com/docx/abc123 done").startswith("https://a.com/docx/")
    assert parse_doc_url("see https://a.com/wiki/abc123 done").startswith("https://a.com/wiki/")


def test_publish_doc_with_wiki_space_two_step(monkeypatch):
    """wiki_space_id 有 → docs+create 拿 token,再 wiki+move,返回 wiki URL。"""
    import larkpub
    calls = []
    def fake_run(cmd):
        calls.append(cmd)
        s = " ".join(cmd)
        if "docs" in s and "+create" in s:
            return 0, "created https://a.com/docx/TOKEN123 done", ""
        if "wiki" in s and "+move" in s:
            return 0, "moved https://a.com/wiki/xyz done", ""
        return 1, "", "err"
    monkeypatch.setattr(larkpub, "_run", fake_run)
    url, kind = larkpub.publish_doc("<title>x</title>", "x", wiki_space_id="sp1")
    assert kind == "wiki"
    assert "/wiki/" in url
    # 确实调了两步
    assert any("docs" in " ".join(c) and "+create" in " ".join(c) for c in calls)
    assert any("wiki" in " ".join(c) and "+move" in " ".join(c) for c in calls)


def test_publish_doc_without_wiki_uses_docs_create(monkeypatch):
    """无 wiki_space_id → 仅 docs +create,返回 docx URL。"""
    import larkpub
    calls = []
    def fake_run(cmd):
        calls.append(cmd)
        return 0, "created https://a.com/docx/abc", ""
    monkeypatch.setattr(larkpub, "_run", fake_run)
    url, kind = larkpub.publish_doc("<title>x</title>", "x")
    assert kind == "docx"
    assert "/docx/" in url
    assert len(calls) == 1    # 只调了 docs+create,没 move


def test_publish_doc_wiki_move_fail_degrades_to_docx(monkeypatch):
    """wiki+move 失败 → 降级返回 docx(不抛错)。"""
    import larkpub
    def fake_run(cmd):
        s = " ".join(cmd)
        if "+create" in s:
            return 0, "created https://a.com/docx/TOKEN123", ""
        return 1, "", "move failed"
    monkeypatch.setattr(larkpub, "_run", fake_run)
    url, kind = larkpub.publish_doc("<title>x</title>", "x", wiki_space_id="sp1")
    assert kind == "docx"     # 降级
    assert "/docx/" in url
```

- [ ] **Step 2: 运行确认失败**

Run: `cd skill-tree/backend && python -m pytest tests/test_larkpub.py -v`
Expected: FAIL — `publish_doc` 返回 str 不是 tuple;URL 正则不匹配 /wiki/。

- [ ] **Step 3: 实现 — 重写 larkpub.py(docs+create → wiki+move 两步)**

> **CLI 实情(已查 `lark-cli wiki +node-create --help`,v1.0.60):** `wiki +node-create` **不接受 `--content`**(只有 `--title`/`--space-id`/`--obj-type` 等),所以不能一步在 wiki 内建带内容的文档。**必须走两步**:`docs +create` 生成文档拿 docx token → `wiki +move` 把它移入 wiki 空间。flag 是 `--space-id`(不是 `--space`)。

先 Read `lark-doc/references/lark-doc-create.md` 与 `lark-wiki/references/lark-wiki-move.md` 确认 `+move` 的源 token 参数名。重写 `larkpub.py`:

```python
"""larkpub.py — 封装 lark-cli subprocess,发布飞书文档(wiki 归档优先)并返回 (url, kind)。"""
from __future__ import annotations
import re
import subprocess

URL_RE = re.compile(r"https?://\S+/(?:docx|wiki)/\S+")
# docx token: docs +create 输出里的 /docx/<token> 段
DOCX_TOKEN_RE = re.compile(r"/docx/([A-Za-z0-9]+)")


def _run(cmd: list[str]) -> tuple[int, str, str]:
    """执行命令，返回 (returncode, stdout, stderr)。外部可被 monkeypatch。"""
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    return p.returncode, p.stdout, p.stderr


def parse_doc_url(output: str) -> str:
    m = URL_RE.search(output)
    return m.group(0).strip() if m else ""


def parse_docx_token(output: str) -> str:
    """从 docs +create 输出里提取 docx token(用于 wiki +move 的 --source-doc)。"""
    m = DOCX_TOKEN_RE.search(output)
    return m.group(1) if m else ""


def publish_doc(xml_content: str, title: str = "学习笔记",
                wiki_space_id: str | None = None) -> tuple[str, str]:
    """发布文档。wiki_space_id 有 → docs+create 拿 token,再 wiki+move 归档到知识库;
    无 → 仅 docs+create。返回 (url, kind:"wiki"|"docx")。失败返回 ("", "")。"""
    # 1) 先 docs +create 拿 docx(无论是否归档 wiki,都需要这份文档)
    create_cmd = ["lark-cli", "docs", "+create", "--as", "user", "--content", xml_content]
    try:
        code, out, err = _run(create_cmd)
    except Exception:
        return "", ""
    if code != 0:
        return "", ""
    docx_url = parse_doc_url(out)
    if not wiki_space_id:
        return docx_url, "docx"
    # 2) wiki +move 归档(读 lark-wiki-move.md 确认 --source 参数名,此处先用 --source-doc)
    token = parse_docx_token(out)
    if not token:
        return docx_url, "docx"    # 拿不到 token,优雅降级为 docx
    # 实现时按 lark-wiki-move.md 的实际 flag 调整(可能是 --source-doc / --src-token)
    move_cmd = ["lark-cli", "wiki", "+move", "--as", "user",
                "--source-doc", token, "--space-id", wiki_space_id]
    try:
        mcode, mout, merr = _run(move_cmd)
    except Exception:
        return docx_url, "docx"    # move 失败,降级
    if mcode == 0:
        wiki_url = parse_doc_url(mout)
        if wiki_url:
            return wiki_url, "wiki"
    return docx_url, "docx"        # move 未产出 wiki url,降级
```

> **实现时必读**:`lark-wiki/references/lark-wiki-move.md` 确认 `+move` 把 Drive docx 移入 wiki 的参数名(`--source-doc` vs `--src-token` vs `--doc-token`),以实际为准调整 `move_cmd`。两步之间用 docx token 串联。整个 wiki 失败链路一律降级为 docx,不抛错。

- [ ] **Step 4: 更新 main.py 的 publish-doc 端点(返回 kind + 透传 wiki_space_id)**

`main.py` 的 `PublishReq` 和 `agent_publish_doc`:

```python
class PublishReq(BaseModel):
    content: str
    title: str = "学习笔记"
    wiki_space_id: str | None = None


@app.post("/api/agent/publish-doc")
def agent_publish_doc(req: PublishReq, x_user_id: str | None = Header(default=None)) -> dict:
    """把 Agent 生成的文档发布到飞书(wiki 归档优先),返回 URL + kind。"""
    # wiki_space_id:请求里有则用;否则查用户配置
    space = req.wiki_space_id
    if not space:
        lark_cfg_p = user_dir(resolve_user(x_user_id)) / "lark_config.json"
        if lark_cfg_p.exists():
            space = _load_json(lark_cfg_p).get("wiki_space_id")
    url, kind = publish_doc(req.content, req.title, wiki_space_id=space)
    if not url:
        raise HTTPException(500, "发布失败：请确认已执行 lark-cli auth login")
    return {"ok": True, "url": url, "kind": kind}
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd skill-tree/backend && python -m pytest tests/test_larkpub.py -v`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
cd "D:\Projects\Resume"
git add skill-tree/backend/larkpub.py skill-tree/backend/main.py skill-tree/backend/tests/test_larkpub.py
git commit -m "feat(lark): publish_doc 支持 wiki 归档 + URL 正则匹配 docx/wiki

wiki_space_id 有则 wiki +node-create 归档到知识库,失败回退 docs +create。
返回 (url, kind)。"
```

---

### Task 13: wiki space 配置端点 + 前端选择器

**Why:** spec §7.2。用户配 wiki_space_id(列空间→选一个→存),产出文档自动归档。

**Files:**
- Modify: `skill-tree/backend/main.py`
- Modify: `skill-tree/frontend/src/api.ts`、`src/panels/SetupPanel.tsx`

- [ ] **Step 1: 后端 — /api/lark/spaces + /api/lark/config 端点**

在 `main.py` 加:

```python
class LarkConfigReq(BaseModel):
    wiki_space_id: str | None = None


def lark_config_path(uid: str) -> Path:
    return user_dir(uid) / "lark_config.json"


@app.get("/api/lark/spaces")
def lark_spaces(x_user_id: str | None = Header(default=None)) -> dict:
    """列出当前用户的飞书知识库空间(调 lark-cli wiki +space-list)。"""
    import subprocess
    try:
        p = subprocess.run(["lark-cli", "wiki", "+space-list", "--as", "user", "--format", "json"],
                           capture_output=True, text=True, timeout=30)
        if p.returncode != 0:
            return {"ok": False, "spaces": [], "error": p.stderr[:200]}
        import json as _json
        # 解析输出里的 spaces 列表(格式以 lark-cli 实际输出为准)
        data = _json.loads(p.stdout) if p.stdout.strip().startswith("{") else {"raw": p.stdout}
        spaces = data.get("data", {}).get("items") or data.get("spaces") or []
        return {"ok": True, "spaces": [{"space_id": s.get("space_id"), "name": s.get("name")} for s in spaces]}
    except Exception as e:
        return {"ok": False, "spaces": [], "error": str(e)}


@app.put("/api/lark/config")
def put_lark_config(req: LarkConfigReq, x_user_id: str | None = Header(default=None)) -> dict:
    uid = resolve_user(x_user_id)
    p = lark_config_path(uid)
    cfg = _load_json(p) if p.exists() else {}
    if req.wiki_space_id is not None:
        cfg["wiki_space_id"] = req.wiki_space_id
    _save_json(p, cfg)
    return {"ok": True, "wiki_space_id": cfg.get("wiki_space_id")}


@app.get("/api/lark/config")
def get_lark_config(x_user_id: str | None = Header(default=None)) -> dict:
    uid = resolve_user(x_user_id)
    p = lark_config_path(uid)
    return _load_json(p) if p.exists() else {"wiki_space_id": None}
```

> `spaces` 解析格式以 `lark-cli wiki +space-list --format json` 实际输出为准,实现时先跑一遍该命令确认 JSON 结构再调字段路径。

- [ ] **Step 2: 前端 api.ts — listWikiSpaces / setWikiSpace / getLarkConfig**

```typescript
export async function listWikiSpaces(): Promise<{ ok: boolean; spaces: { space_id: string; name: string }[]; error?: string }> {
  const res = await fetch(`${API}/lark/spaces`, { headers: { 'X-User-Id': getUserId() } })
  return res.json()
}

export async function setWikiSpace(spaceId: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${API}/lark/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', 'X-User-Id': getUserId() },
    body: JSON.stringify({ wiki_space_id: spaceId }),
  })
  return res.json()
}

export async function getLarkConfig(): Promise<{ wiki_space_id: string | null }> {
  const res = await fetch(`${API}/lark/config`, { headers: { 'X-User-Id': getUserId() } })
  return res.json()
}
```

- [ ] **Step 3: 前端 SetupPanel.tsx — wiki space 选择器**

先 Read `SetupPanel.tsx` 了解布局,在合适位置(如 LLM 配置区附近)加一个「飞书知识库归档」区块:下拉列出 spaces(listWikiSpaces)→ 选中 setWikiSpace。UI 简洁:

```typescript
// 在 SetupPanel 内
const [spaces, setSpaces] = useState<{space_id:string;name:string}[]>([])
const [curSpace, setCurSpace] = useState<string | null>(null)
useEffect(() => {
  getLarkConfig().then(c => setCurSpace(c.wiki_space_id))
  listWikiSpaces().then(r => setSpaces(r.spaces || []))
}, [])
// 渲染:<select> 列 spaces,onChange → setWikiSpace(id) → setCurSpace(id)
```

(具体 JSX 按 SetupPanel 现有风格写。)

- [ ] **Step 4: 前端构建确认**

Run: `cd skill-tree/frontend && npm run build`
Expected: 构建成功。

- [ ] **Step 5: 提交**

```bash
cd "D:\Projects\Resume"
git add skill-tree/backend/main.py skill-tree/frontend/src/api.ts skill-tree/frontend/src/panels/SetupPanel.tsx
git commit -m "feat(lark): wiki space 配置端点 + 前端选择器

/api/lark/spaces 列空间、/api/lark/config 存取;SetupPanel 选 wiki 归档目标。"
```

---

### Task 14: Writer 三模板差异化 + doc_type 判定 + 前端 DocCard 标识

**Why:** spec §7.4。`_run_writer` 不写死 note,按关键词判 doc_type,三模板各自有 few-shot(已在 Task 5 的 Writer prompt 里?需确认),前端 DocCard 显示类型 + wiki/docx。

**Files:**
- Modify: `skill-tree/backend/agent/loop.py`(`_run_writer`)
- Modify: `skill-tree/backend/agent/prompts.py`(Writer 按 doc_type 选模板——若 Task 5 未做)
- Modify: `skill-tree/frontend/src/DocCard.tsx`

- [ ] **Step 1: 写失败测试 — doc_type 判定**

在 `tests/test_loop.py` 追加:

```python
def test_run_writer_picks_doc_type_by_keyword():
    """含'复习'→review,含'周报'→weekly,否则 note。"""
    from agent.loop import _pick_doc_type
    assert _pick_doc_type("帮我生成复习卡") == "review"
    assert _pick_doc_type("整理本周学习周报") == "weekly"
    assert _pick_doc_type("整理个 DeepFM 笔记") == "note"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd skill-tree/backend && python -m pytest tests/test_loop.py::test_run_writer_picks_doc_type_by_keyword -v`
Expected: FAIL — `_pick_doc_type` 不存在。

- [ ] **Step 3: 实现 — _pick_doc_type + 重写 _run_writer**

`agent/loop.py` 加:

```python
def _pick_doc_type(request: str) -> str:
    r = request
    if any(k in r for k in ("复习", "背", "默写", "review")):
        return "review"
    if any(k in r for k in ("周报", "本周", "总结", "weekly")):
        return "weekly"
    return "note"
```

重写 `_run_writer`(原 loop.py:258-268):

```python
def _run_writer(ctx, user_input, executor_messages, chat_fn, cfg) -> Iterator[dict]:
    from agent.prompts import render_writer
    doc_type = _pick_doc_type(user_input)
    materials = "\n".join(m.get("content", "") for m in executor_messages
                          if m.get("role") == "user" and "Observation" in m.get("content", ""))
    sys_w = render_writer(materials=materials[:2000], request=user_input, doc_type=doc_type)
    try:
        res = chat_fn(cfg, [{"role": "system", "content": sys_w},
                            {"role": "user", "content": f"请生成{doc_type}类型文档。"}], tools=None)
        content = res.get("content", "")
        # 标题:取第一个 <title> 或用 doc_type
        title = (content.split("</title>")[0].split("<title>")[-1]
                 if "<title>" in content else {"note": "学习笔记", "review": "复习卡", "weekly": "周报"}[doc_type])
        yield {"type": "doc_card", "doc_type": doc_type, "content": content, "title": title}
    except Exception as e:
        yield {"type": "error", "content": f"文档生成失败: {e}"}
```

`prompts.py` 的 `render_writer` 增 doc_type 参数,并按 doc_type 强调对应模板(若 Task 5 已加模板差异化则只改签名):

```python
def render_writer(materials: str, request: str, doc_type: str = "note") -> str:
    return SYS_WRITER.format(materials=materials, request=request, doc_type=doc_type)
```

`SYS_WRITER` 里把「文档类型模板」段加一句 `本次生成类型：{doc_type}(note/review/weekly 之一,严格按对应模板结构输出)`。

- [ ] **Step 4: 前端 DocCard.tsx — 显示 doc_type + 接受 title/kind**

先 Read `DocCard.tsx`,改 Props 接 `docType`、`title`、`kind`;发布后用 Task 12 返回的 url+kind 显示「Wiki 归档」或「飞书文档」链接。AgentChat.tsx 传 doc_type 给 DocCard(Task 10 已 map doc_card 事件)。

- [ ] **Step 5: 运行测试 + 前端构建**

Run: `cd skill-tree/backend && python -m pytest tests/test_loop.py -k "doc_type" -v && cd ../frontend && npm run build`
Expected: 测试 PASS + 构建成功。

- [ ] **Step 6: 提交**

```bash
cd "D:\Projects\Resume"
git add skill-tree/backend/agent/loop.py skill-tree/backend/agent/prompts.py skill-tree/backend/tests/test_loop.py skill-tree/frontend/src/DocCard.tsx skill-tree/frontend/src/AgentChat.tsx
git commit -m "feat(agent): Writer 三模板差异化(doc_type 判定 + 标题)

按关键词判 note/review/weekly;Writer prompt 按 doc_type 强调对应结构;
doc_card 事件带 doc_type + title;DocCard 显示类型标识。"
```

---

## Phase 8 — 收尾

### Task 15: 端到端冒烟 + README 更新

**Why:** 确认全链路通,补 README 的 lark-cli 配置说明(spec §7.1 约束)。

**Files:**
- Modify: `skill-tree/README.md`

- [ ] **Step 1: 后端全量测试**

Run: `cd skill-tree/backend && python -m pytest tests/ -q`
Expected: 全 PASS(原 78 + 新增)。

- [ ] **Step 2: 前端构建**

Run: `cd skill-tree/frontend && npm run build`
Expected: 构建成功。

- [ ] **Step 3: README 补 lark-cli + wiki 配置说明**

在 `skill-tree/README.md` 的 AI/Agent 配置段加:

```markdown
## 飞书文档归档(可选)

Agent 产出的学习笔记/复习卡/周报可发布到飞书:

1. 安装并登录 lark-cli:`lark-cli auth login`
2. 在「设置」→「飞书知识库归档」选择一个 wiki 空间(或留空,仅生成单篇文档)
3. 对话里说「整理个 X 的笔记」「生成复习卡」「本周周报」,Agent 产出文档卡片,点「写飞书」即归档
```

- [ ] **Step 4: 手动冒烟(可选,有 lark-cli + LLM 配置时)**

启动后端 + 前端,测三条路径:
1. chat:「你好」→ 直接回答(无工具气泡)
2. query:「我学到哪了」→ 调 get_progress → 回答
3. produce:「整理个 DeepFM 笔记」→ Writer 产 doc_card → 点写飞书 → 飞书 wiki/docx 链接

- [ ] **Step 5: 提交**

```bash
cd "D:\Projects\Resume"
git add skill-tree/README.md
git commit -m "docs: README 补飞书文档归档配置说明"
```

---

## 完成标准

- [ ] 后端全量测试 PASS
- [ ] 前端构建无报错
- [ ] 四块空心全兑现:记忆(history 注入)/ 短路(chat 直答)/ 提案(node_proposal 卡片+apply)/ Reflexion(Reflect 校验)
- [ ] Prompt 工程:三套 few-shot + 正则解析 + 回归测试
- [ ] doc→wiki:publish_doc 支持 wiki 归档 + 配置端点 + 前端选择器
- [ ] 面试可讲:每个能力都有对应的 commit + 测试佐证
