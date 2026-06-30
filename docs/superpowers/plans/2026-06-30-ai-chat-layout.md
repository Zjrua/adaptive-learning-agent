# AI 对话区改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 AI 从右下角悬浮 FAB 改造为系统一等公民——桌面三栏常驻对话区、多会话（`/new` + 历史切换 + LLM 标题）、跨会话搜索与 JSON 导出、符号引用（#/@/$）、全链路真流式、Markdown 渲染。

**Architecture:** 后端新增 `chat_store.py`（多会话存储 + 搜索 + 导出 + 引用解析，纯函数 TDD）+ main.py 挂 7 个 chat 端点；loop.py 改流式（最终回答 yield delta）+ 引用预处理注入。前端删 `AgentChat.tsx` 旧 FAB 逻辑重写为响应式对话区，新增 `Markdown.tsx`/`ChatToolbar.tsx`/`MentionInput.tsx`，App 改三栏 grid。

**Tech Stack:** Python 3.14 / FastAPI / pytest（已有）/ React+TS / marked + dompurify + highlight.js。

---

## 文件结构

```
backend/
├── chat_store.py        【新】多会话存储/搜索/导出/引用解析(纯函数,TDD)
├── main.py              【改】挂 chat 端点(history/sync/title/search/export/resolve/suggest)
├── agent/loop.py        【改】引用预处理注入 + 最终回答流式 yield delta
└── tests/
    └── test_chat_store.py  【新】

frontend/src/
├── AgentChat.tsx        【重写】FAB → 响应式对话区(常驻 dock / 全屏 page)
├── ChatMessage.tsx      【改】流式光标 + Markdown 渲染 + 引用 chip
├── Markdown.tsx         【新】marked + DOMPurify + highlight.js
├── ChatToolbar.tsx      【新】工具条(会话下拉/搜索/导出/折叠)
├── MentionInput.tsx     【新】输入框 + #/@/$ 补全弹层
├── api.ts               【改】chat 全套端点
├── types.ts             【改】Session/ChatHistory/Ref 类型
├── App.tsx              【改】三栏 grid + 删 FAB + #chat 路由
└── index.css            【改】三栏 + .md + AI 栏 + mention 样式
```

**实施顺序（4 阶段，每阶段独立可测）：**
- **阶段一 后端 chat 存储**（chat_store.py + 端点，纯函数 TDD）
- **阶段二 loop 流式 + 引用**（loop.py 改造）
- **阶段三 前端基础**（依赖安装 + Markdown + 三栏布局 + 删 FAB）
- **阶段四 前端高级**（多会话 + 搜索导出 + 符号引用 + 流式渲染）

---

# 阶段一：后端 chat 存储（纯函数 TDD）

## Task 1: chat_store 多会话数据模型 + CRUD

**Files:**
- Create: `skill-tree/backend/chat_store.py`
- Test: `skill-tree/backend/tests/test_chat_store.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_chat_store.py
from __future__ import annotations
import time
from pathlib import Path

from chat_store import ChatStore


def _new_store(tmp_path: Path) -> ChatStore:
    return ChatStore(tmp_path / "chat_history.json")


def test_new_store_has_empty_state(tmp_path: Path):
    s = _new_store(tmp_path)
    state = s.load()
    assert state["sessions"] == []
    assert state["current_session_id"] is None


def test_new_session_sets_current(tmp_path: Path):
    s = _new_store(tmp_path)
    sid = s.new_session()
    state = s.load()
    assert state["current_session_id"] == sid
    assert len(state["sessions"]) == 1
    assert state["sessions"][0]["id"] == sid
    assert state["sessions"][0]["messages"] == []
    assert state["sessions"][0]["title"] == "新会话"


def test_append_message_to_current(tmp_path: Path):
    s = _new_store(tmp_path)
    sid = s.new_session()
    s.append_message(sid, {"role": "user", "content": "你好", "ts": "2026-06-30T10:00:00"})
    msgs = s.load()["sessions"][0]["messages"]
    assert len(msgs) == 1
    assert msgs[0]["content"] == "你好"


def test_switch_current_session(tmp_path: Path):
    s = _new_store(tmp_path)
    s1 = s.new_session()
    s2 = s.new_session()
    assert s.load()["current_session_id"] == s2
    s.set_current(s1)
    assert s.load()["current_session_id"] == s1


def test_delete_session(tmp_path: Path):
    s = _new_store(tmp_path)
    s1 = s.new_session()
    s.delete_session(s1)
    assert s.load()["sessions"] == []


def test_set_title(tmp_path: Path):
    s = _new_store(tmp_path)
    sid = s.new_session()
    s.set_title(sid, "DeepFM 学习")
    assert s.load()["sessions"][0]["title"] == "DeepFM 学习"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd skill-tree/backend && python -m pytest tests/test_chat_store.py -q`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现 `chat_store.py`**

```python
"""chat_store.py — 多会话对话存储（JSON 文件，每用户独立）。

数据模型: {sessions: [Session], current_session_id: str|null}
Session: {id, title, created_at, updated_at, messages: [Msg]}
Msg: {role, content, ts, events?: [...]}
"""
from __future__ import annotations
import json
import time
from pathlib import Path


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class ChatStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> dict:
        if not self.path.exists():
            return {"sessions": [], "current_session_id": None, "updated_at": _now()}
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, state: dict) -> None:
        state["updated_at"] = _now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def new_session(self) -> str:
        state = self.load()
        sid = f"s_{int(time.time() * 1000)}"
        state["sessions"].append({
            "id": sid, "title": "新会话", "created_at": _now(),
            "updated_at": _now(), "messages": [],
        })
        state["current_session_id"] = sid
        self._save(state)
        return sid

    def append_message(self, session_id: str, msg: dict) -> None:
        state = self.load()
        for s in state["sessions"]:
            if s["id"] == session_id:
                s["messages"].append(msg)
                s["updated_at"] = _now()
                break
        self._save(state)

    def set_current(self, session_id: str) -> None:
        state = self.load()
        state["current_session_id"] = session_id
        self._save(state)

    def set_title(self, session_id: str, title: str) -> None:
        state = self.load()
        for s in state["sessions"]:
            if s["id"] == session_id:
                s["title"] = title
                break
        self._save(state)

    def delete_session(self, session_id: str) -> None:
        state = self.load()
        state["sessions"] = [s for s in state["sessions"] if s["id"] != session_id]
        if state["current_session_id"] == session_id:
            state["current_session_id"] = state["sessions"][0]["id"] if state["sessions"] else None
        self._save(state)

    def replace_all(self, sessions: list, current_session_id: str | None) -> None:
        """双写同步：前端发回完整数据，后端覆盖。"""
        self._save({"sessions": sessions, "current_session_id": current_session_id})
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd skill-tree/backend && python -m pytest tests/test_chat_store.py -q`
Expected: PASS（6 passed）

- [ ] **Step 5: Commit**

```bash
git add skill-tree/backend/chat_store.py skill-tree/backend/tests/test_chat_store.py
git commit -m "feat(chat): 多会话存储 CRUD"
```

---

## Task 2: 跨会话搜索 + JSON 导出

**Files:**
- Modify: `skill-tree/backend/chat_store.py`
- Test: `skill-tree/backend/tests/test_chat_store.py`（追加）

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/test_chat_store.py
def test_search_across_sessions(tmp_path: Path):
    s = _new_store(tmp_path)
    s1 = s.new_session()
    s.set_title(s1, "推荐学习")
    s.append_message(s1, {"role": "user", "content": "DeepFM 怎么实现", "ts": "x"})
    s.append_message(s1, {"role": "assistant", "content": "DeepFM 是华为提出", "ts": "x"})
    s2 = s.new_session()
    s.set_title(s2, "面试准备")
    s.append_message(s2, {"role": "user", "content": "DeepFM 面试题", "ts": "x"})

    hits = s.search("DeepFM")
    assert len(hits) == 3  # 3 条消息命中
    # 每条带 session_id/title/snippet
    assert all("session_id" in h and "snippet" in h and "session_title" in h for h in hits)
    assert any(h["session_title"] == "推荐学习" for h in hits)


def test_search_no_match(tmp_path: Path):
    s = _new_store(tmp_path)
    s1 = s.new_session()
    s.append_message(s1, {"role": "user", "content": "你好", "ts": "x"})
    assert s.search("不存在的内容") == []


def test_export_session_json(tmp_path: Path):
    s = _new_store(tmp_path)
    s1 = s.new_session()
    s.set_title(s1, "测试会话")
    s.append_message(s1, {"role": "user", "content": "hi", "ts": "x"})
    data = s.export(session_id=s1)
    assert data["title"] == "测试会话"
    assert len(data["messages"]) == 1
    assert data["messages"][0]["content"] == "hi"


def test_export_all_json(tmp_path: Path):
    s = _new_store(tmp_path)
    s.new_session()
    s.new_session()
    data = s.export(session_id=None)
    assert "sessions" in data
    assert len(data["sessions"]) == 2
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd skill-tree/backend && python -m pytest tests/test_chat_store.py::test_search_across_sessions -q`
Expected: FAIL（`AttributeError: 'ChatStore' object has no attribute 'search'`）

- [ ] **Step 3: 实现 search + export**

追加到 `chat_store.py` 的 `ChatStore` 类内：

```python
    def search(self, query: str) -> list[dict]:
        """跨所有会话子串搜索消息。返回 [{session_id, session_title, message_index, role, snippet}]。"""
        if not query.strip():
            return []
        q = query.lower()
        hits = []
        for s in self.load()["sessions"]:
            for i, m in enumerate(s["messages"]):
                content = m.get("content", "")
                if q in content.lower():
                    idx = content.lower().find(q)
                    start = max(0, idx - 15)
                    snippet = content[start:start + len(q) + 30]
                    hits.append({
                        "session_id": s["id"], "session_title": s["title"],
                        "message_index": i, "role": m.get("role", ""),
                        "snippet": ("…" if start > 0 else "") + snippet,
                    })
        return hits

    def export(self, session_id: str | None) -> dict:
        """导出为 JSON 可序列化结构。session_id=None 导出全部。"""
        state = self.load()
        if session_id is None:
            return {"sessions": state["sessions"], "exported_at": _now()}
        for s in state["sessions"]:
            if s["id"] == session_id:
                return {**s, "exported_at": _now()}
        return {}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd skill-tree/backend && python -m pytest tests/test_chat_store.py -q`
Expected: PASS（10 passed）

- [ ] **Step 5: Commit**

```bash
git add skill-tree/backend/chat_store.py skill-tree/backend/tests/test_chat_store.py
git commit -m "feat(chat): 跨会话搜索 + JSON 导出"
```

---

## Task 3: 符号引用解析（#/@/$）

**Files:**
- Modify: `skill-tree/backend/chat_store.py`
- Test: `skill-tree/backend/tests/test_chat_store.py`（追加）

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/test_chat_store.py
def test_resolve_node_ref(tmp_path: Path):
    s = _new_store(tmp_path)
    # graph: 节点列表
    graph = {"nodes": [{"id": "deepfm", "name": "DeepFM", "category": "特征交叉",
                         "tasks": [{"title": "读论文"}], "depends_on": ["fm"]}]}
    refs = s.resolve_refs("#deepfm", graph=graph, dirs=[], resources=[])
    assert len(refs) == 1
    assert refs[0]["type"] == "node"
    assert "DeepFM" in refs[0]["content"]


def test_resolve_dir_ref(tmp_path: Path):
    s = _new_store(tmp_path)
    dirs = [{"id": "recommendation", "title": "推荐算法", "icon": "🎯", "color": "#4ade80"}]
    refs = s.resolve_refs("$推荐", graph={"nodes": []}, dirs=dirs, resources=[])
    assert len(refs) == 1
    assert refs[0]["type"] == "dir"
    assert "推荐算法" in refs[0]["content"]


def test_resolve_resource_ref(tmp_path: Path):
    s = _new_store(tmp_path)
    resources = [{"id": "dssm_paper", "label": "DSSM 论文", "url": "https://arxiv.org/abs/xxx"}]
    refs = s.resolve_refs("@dssm", graph={"nodes": []}, dirs=[], resources=resources)
    assert len(refs) == 1
    assert refs[0]["type"] == "resource"


def test_resolve_unknown_returns_empty(tmp_path: Path):
    s = _new_store(tmp_path)
    refs = s.resolve_refs("#不存在的节点", graph={"nodes": []}, dirs=[], resources=[])
    assert refs == []


def test_suggest_nodes_by_prefix(tmp_path: Path):
    s = _new_store(tmp_path)
    graph = {"nodes": [{"id": "deepfm", "name": "DeepFM"}, {"id": "dcn", "name": "DCN"}]}
    out = s.suggest("node", "deep", graph=graph, dirs=[], resources=[])
    assert len(out) == 1
    assert out[0]["id"] == "deepfm"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd skill-tree/backend && python -m pytest tests/test_chat_store.py::test_resolve_node_ref -q`
Expected: FAIL（`AttributeError: 'ChatStore' object has no attribute 'resolve_refs'`）

- [ ] **Step 3: 实现 resolve_refs + suggest**

追加到 `chat_store.py` 的 `ChatStore` 类内（顶部加 `import re`）：

```python
    # ── 符号引用 ──
    # 形如 #node_id  @resource_id  $dir_keyword
    _REF_RE = re.compile(r"([#@$])([^\s#@$，。、]+)")

    def resolve_refs(self, text: str, graph: dict, dirs: list, resources: list) -> list[dict]:
        """解析文本里的 #/@/$ 引用，返回各对象展开内容 [{type, id, content}]。"""
        out = []
        seen = set()
        for m in self._REF_RE.finditer(text):
            sym, key = m.group(1), m.group(2).lower()
            tag = (sym, key)
            if tag in seen:
                continue
            seen.add(tag)
            if sym == "#":
                for n in graph.get("nodes", []):
                    if key in (n.get("id", "").lower(), n.get("name", "").lower()):
                        tasks = ", ".join(t.get("title", "") for t in n.get("tasks", []))
                        out.append({"type": "node", "id": n.get("id"), "name": n.get("name"),
                                    "content": f"[节点] {n.get('name')}({n.get('category','')}), "
                                               f"依赖: {n.get('depends_on',[])}, 任务: {tasks}"})
                        break
            elif sym == "$":
                for d in dirs:
                    if key in d.get("id", "").lower() or key in d.get("title", "").lower():
                        out.append({"type": "dir", "id": d.get("id"), "name": d.get("title"),
                                    "content": f"[方向] {d.get('title')} {d.get('icon','')}"})
                        break
            elif sym == "@":
                for r in resources:
                    if key in r.get("id", "").lower() or key in r.get("label", "").lower():
                        out.append({"type": "resource", "id": r.get("id"), "name": r.get("label"),
                                    "content": f"[资源] {r.get('label')}: {r.get('url','')}"})
                        break
        return out

    def suggest(self, ref_type: str, prefix: str, graph: dict, dirs: list, resources: list) -> list[dict]:
        """mention 补全：按类型 + 前缀模糊匹配。返回 [{id, name, label?}]。"""
        p = prefix.lower()
        out = []
        if ref_type == "node":
            for n in graph.get("nodes", []):
                if p in n.get("id", "").lower() or p in n.get("name", "").lower():
                    out.append({"id": n.get("id"), "name": n.get("name")})
        elif ref_type == "dir":
            for d in dirs:
                if p in d.get("id", "").lower() or p in d.get("title", "").lower():
                    out.append({"id": d.get("id"), "name": d.get("title")})
        elif ref_type == "resource":
            for r in resources:
                if p in r.get("id", "").lower() or p in r.get("label", "").lower():
                    out.append({"id": r.get("id"), "name": r.get("label")})
        return out[:8]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd skill-tree/backend && python -m pytest tests/test_chat_store.py -q`
Expected: PASS（15 passed）

- [ ] **Step 5: Commit**

```bash
git add skill-tree/backend/chat_store.py skill-tree/backend/tests/test_chat_store.py
git commit -m "feat(chat): 符号引用解析(#/@/$) + mention 补全"
```

---

## Task 4: main.py 挂 chat 端点

**Files:**
- Modify: `skill-tree/backend/main.py`
- Test: 手动 curl 冒烟

- [ ] **Step 1: 顶部加导入**

在 `from larkpub import publish_doc` 之后加：

```python
from chat_store import ChatStore
```

- [ ] **Step 2: 加 chat 路径常量 + 辅助**

在 `def rag_index_dir` 之后加：

```python
def chat_store_path(uid: str) -> Path:
    return user_dir(uid) / "chat_history.json"


def chat_store(uid: str) -> ChatStore:
    return ChatStore(chat_store_path(uid))
```

- [ ] **Step 3: 加 chat 端点（插在 publish_doc 端点之后、「其他板块」之前）**

```python
# ─────────────────────────── Chat 对话管理 ───────────────────────────
@app.get("/api/chat/history")
def get_chat_history(x_user_id: str | None = Header(default=None)) -> dict:
    uid = resolve_user(x_user_id)
    return chat_store(uid).load()


class ChatSyncReq(BaseModel):
    sessions: list
    current_session_id: str | None = None


@app.post("/api/chat/sync")
def chat_sync(req: ChatSyncReq, x_user_id: str | None = Header(default=None)) -> dict:
    uid = resolve_user(x_user_id)
    chat_store(uid).replace_all(req.sessions, req.current_session_id)
    return {"ok": True}


class ChatTitleReq(BaseModel):
    message: str


@app.post("/api/chat/title")
def chat_title(req: ChatTitleReq, x_user_id: str | None = Header(default=None)) -> dict:
    """LLM 生成会话标题。失败回退首句截断。"""
    uid = resolve_user(x_user_id)
    cfg = _load_json(llm_config_path(uid)) if llm_config_path(uid).exists() else {}
    fallback = req.message.strip().replace("\n", " ")[:20] or "新会话"
    if not cfg.get("api_key"):
        return {"title": fallback}
    try:
        from agent.protocol import chat_with_tools
        res = chat_with_tools(cfg, [
            {"role": "system", "content": "给下面的用户消息起一个 4-10 字的对话标题，只输出标题，不要标点。"},
            {"role": "user", "content": req.message[:200]},
        ], tools=None, temperature=0.3)
        title = res.get("content", "").strip().replace("\n", "")[:20]
        return {"title": title or fallback}
    except Exception:
        return {"title": fallback}


@app.get("/api/chat/search")
def chat_search(q: str, x_user_id: str | None = Header(default=None)) -> dict:
    uid = resolve_user(x_user_id)
    return {"hits": chat_store(uid).search(q)}


@app.get("/api/chat/export")
def chat_export(session_id: str | None = None, x_user_id: str | None = Header(default=None) | None = None):
    uid = resolve_user(x_user_id)
    return chat_store(uid).export(session_id)


def _collect_resources(trees: list) -> list:
    """从技能树收集所有资源(论文链接/源码路径)供 @ 引用。"""
    out = []
    for t in trees:
        for b in t.get("branches", []):
            for n in b.get("nodes", []):
                for tk in n.get("tasks", []):
                    if tk.get("resource"):
                        out.append({"id": f"{n['id']}_{tk.get('id','')}",
                                    "label": f"{n.get('name')}·{tk.get('title','')}",
                                    "url": tk["resource"]})
    return out


@app.get("/api/chat/resolve")
def chat_resolve(refs: str, x_user_id: str | None = Header(default=None)) -> dict:
    uid = resolve_user(x_user_id)
    trees = load_trees(user_dir(uid))
    lay = layout_mod.compute_layout(trees)
    dirs = [{"id": t["tree_id"], "title": t.get("title", ""), "icon": t.get("icon", ""),
             "color": t.get("color", "")} for t in lay["dir_order"]]
    graph = {"nodes": lay["nodes"]}
    resources = _collect_resources(trees)
    return {"resolved": chat_store(uid).resolve_refs(refs, graph, dirs, resources)}


@app.get("/api/chat/suggest")
def chat_suggest(type: str, q: str, x_user_id: str | None = Header(default=None)) -> dict:
    uid = resolve_user(x_user_id)
    trees = load_trees(user_dir(uid))
    lay = layout_mod.compute_layout(trees)
    dirs = [{"id": t["tree_id"], "title": t.get("title", "")} for t in lay["dir_order"]]
    graph = {"nodes": lay["nodes"]}
    resources = _collect_resources(trees)
    return {"items": chat_store(uid).suggest(type, q, graph, dirs, resources)}
```

> 注意：`chat_export` 端点的参数签名里 `Header(default=None) | None` 有笔误，应写成 `x_user_id: str | None = Header(default=None)`。实现时用正确签名：
> ```python
> @app.get("/api/chat/export")
> def chat_export(session_id: str | None = None, x_user_id: str | None = Header(default=None)) -> dict:
>     uid = resolve_user(x_user_id)
>     return chat_store(uid).export(session_id)
> ```

- [ ] **Step 4: 启动后端冒烟**

```bash
cd skill-tree/backend && python -m uvicorn main:app --port 8000 &
sleep 3
curl -s http://localhost:8000/api/chat/history -H "X-User-Id: default"    # {sessions:[],...}
curl -s "http://localhost:8000/api/chat/search?q=test" -H "X-User-Id: default"  # {hits:[]}
curl -s "http://localhost:8000/api/chat/suggest?type=node&q=deep" -H "X-User-Id: default"
```

- [ ] **Step 5: Commit**

```bash
git add skill-tree/backend/main.py
git commit -m "feat(chat): 挂载 chat 端点(history/sync/title/search/export/resolve/suggest)"
```

---

# 阶段二：loop 流式 + 引用注入

## Task 5: loop 引用预处理注入

**Files:**
- Modify: `skill-tree/backend/agent/loop.py`
- Test: `skill-tree/backend/tests/test_loop.py`（追加）

- [ ] **Step 1: 追加失败测试**

```python
# 追加到 tests/test_loop.py
from agent.loop import extract_refs, inject_refs


def test_extract_refs_finds_all_symbols():
    text = "帮我讲讲 #deepfm 和 @dssm论文 以及 $推荐"
    refs = extract_refs(text)
    assert ("#", "deepfm") in refs
    assert ("@", "dssm论文") in refs
    assert ("$", "推荐") in refs


def test_inject_refs_appends_context():
    sys_msg = "你是助手。"
    refs_ctx = "[节点] DeepFM(特征交叉), 依赖: ['fm']"
    out = inject_refs(sys_msg, refs_ctx)
    assert "用户引用了以下内容" in out
    assert refs_ctx in out


def test_inject_refs_empty_returns_unchanged():
    assert inject_refs("原文", "") == "原文"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd skill-tree/backend && python -m pytest tests/test_loop.py::test_extract_refs_finds_all_symbols -q`
Expected: FAIL（`ImportError`）

- [ ] **Step 3: 实现 extract_refs + inject_refs**

在 `loop.py` 顶部（`parse_react` 之前）加：

```python
_REF_RE = re.compile(r"([#@$])([^\s#@$，。、]+)")


def extract_refs(text: str) -> list[tuple[str, str]]:
    """提取文本里的 #/@/$ 引用，返回 [(symbol, key), ...]，去重保序。"""
    seen = set()
    out = []
    for m in _REF_RE.finditer(text):
        tag = (m.group(1), m.group(2))
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def inject_refs(system_prompt: str, refs_context: str) -> str:
    """把引用解析出的上下文注入 system prompt。无引用则原样返回。"""
    if not refs_context.strip():
        return system_prompt
    return system_prompt + "\n\n用户引用了以下内容（作为额外上下文）：\n" + refs_context
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd skill-tree/backend && python -m pytest tests/test_loop.py -q`
Expected: PASS（含原有 + 3 新增）

- [ ] **Step 5: 在 run_agent 里接线（注入引用上下文）**

修改 `run_agent` 的 Executor 段，在构造 `messages` 之前注入。在 `sys_e = render_executor(...)` 之后加：

```python
    # 引用预处理：解析用户消息里的 #/@/$ 并注入上下文
    refs_text = ""
    if hasattr(ctx, "resolve_refs_fn") and ctx.resolve_refs_fn:
        from agent.loop import extract_refs
        refs = extract_refs(user_input)
        if refs:
            refs_str = " ".join(f"{s}{k}" for s, k in refs)
            resolved = ctx.resolve_refs_fn(refs_str)
            refs_text = "\n".join(r.get("content", "") for r in resolved)
    sys_e = inject_refs(sys_e, refs_text)
```

- [ ] **Step 6: Commit**

```bash
git add skill-tree/backend/agent/loop.py skill-tree/backend/tests/test_loop.py
git commit -m "feat(agent): 引用预处理注入(#/@/$ 解析到 system prompt)"
```

---

## Task 6: loop 最终回答流式（yield delta）

**Files:**
- Modify: `skill-tree/backend/agent/loop.py`

> 此任务无新单测（流式改造靠端到端验证），但要确保现有 loop 测试不破。

- [ ] **Step 1: 在 loop.py 加流式最终回答辅助函数**

在 `_run_writer` 之前加：

```python
def _stream_final(ctx, messages, chat_fn, cfg) -> "Iterator[dict]":
    """流式产出最终回答：用 chat_fn 的流式模式逐 token yield delta。
    回退：若 chat_fn 不支持流式，降级为一次性 final_answer。"""
    # 构造一个"请基于以上信息给出最终回答"的提示
    stream_messages = list(messages) + [
        {"role": "user", "content": "请基于以上思考和检索结果，给出最终回答（中文，可用 markdown）。"}]
    try:
        chunks = chat_fn(cfg, stream_messages, tools=None, stream=True)
        # chat_fn 流式返回迭代器（FakeChat）或协议层 chat_stream
        for ev in chunks:
            if isinstance(ev, dict) and ev.get("type") == "delta":
                yield {"type": "delta", "content": ev["content"]}
        yield {"type": "final_done"}
        return
    except TypeError:
        # chat_fn 不接受 stream 参数 → 降级
        pass
    except Exception:
        pass
    # 降级：非流式一次性返回
    try:
        res = chat_fn(cfg, stream_messages, tools=None)
        yield {"type": "delta", "content": res.get("content", "")}
    except Exception as e:
        yield {"type": "delta", "content": f"（生成失败: {e}）"}
    yield {"type": "final_done"}
```

- [ ] **Step 2: 替换 Executor 的 final_answer yield**

把 `run_agent` 里这段：

```python
        if step["type"] == "final":
            yield {"type": "final_answer", "content": step["answer"]}
            break
```

改为：

```python
        if step["type"] == "final":
            # 流式产出最终回答；step["answer"] 是模型在 ReAct 里给的草稿，
            # 用一次专门的流式调用逐字输出。降级时回退 final_answer。
            if step.get("answer") and not step["answer"].startswith("（已达到最大"):
                yield from _stream_final(ctx, messages, chat_fn, cfg)
            else:
                yield {"type": "final_answer", "content": step["answer"]}
            break
```

> 注意：保留 `final_answer` 事件类型作降级兜底，前端同时处理 `delta` + `final_done` 和 `final_answer`。

- [ ] **Step 3: 跑全量后端测试确认不破**

Run: `cd skill-tree/backend && python -m pytest tests/ -q`
Expected: 全绿（现有 loop 测试用 FakeChat，`_stream_final` 会走 FakeChat 的 stream 分支）

> **重要**：现有 `test_loop_chat_intent_short_circuits` / `test_loop_tool_step_then_final` 断言 `"final_answer" in types`，流式改造后事件变成多个 `delta` + `final_done`（无 final_answer），这两个测试会失败。**需调整这两个测试的断言**：把 `assert "final_answer" in types` 改为 `assert "delta" in types and "final_done" in types`，并把 `any("加油" in e.get("content","") for e in events if e["type"]=="final_answer")` 改为聚合所有 delta 的 content 后再断言：
> ```python
> # 改 test_loop_chat_intent_short_circuits 的断言:
> full = "".join(e.get("content","") for e in events if e["type"]=="delta")
> assert "delta" in types and "final_done" in types
> assert "加油" in full
> assert "done" in types
> ```
> 同理改 `test_loop_tool_step_then_final`：`assert any(e["type"]=="delta" for e in events)` + `assert any(e["type"]=="final_done" for e in events)`。
> `test_loop_max_steps_guard` 不受影响（走降级 final_answer 分支）。

- [ ] **Step 4: 端到端冒烟（流式）**

```bash
cd skill-tree/backend && python -m uvicorn main:app --port 8000 &
sleep 3
python -c "
import urllib.request, json
req = urllib.request.Request('http://localhost:8000/api/agent/chat',
    data=json.dumps({'message':'你好'}).encode('utf-8'),
    headers={'X-User-Id':'default','Content-Type':'application/json'}, method='POST')
resp = urllib.request.urlopen(req, timeout=40)
types = []
buf = b''
while True:
    chunk = resp.read(4096)
    if not chunk: break
    buf += chunk
    while b'\n\n' in buf:
        block, buf = buf.split(b'\n\n', 1)
        line = block.decode('utf-8').strip()
        if line.startswith('data: '):
            ev = json.loads(line[6:])
            types.append(ev['type'])
print('事件序列:', ' -> '.join(types))
# 期望含 delta(多个) 和 final_done
"
```

- [ ] **Step 5: Commit**

```bash
git add skill-tree/backend/agent/loop.py
git commit -m "feat(agent): 最终回答全链路流式(yield delta + final_done)"
```

---

# 阶段三：前端基础（依赖 + Markdown + 三栏布局）

## Task 7: 安装前端依赖 + Markdown 组件

**Files:**
- Create: `skill-tree/frontend/src/Markdown.tsx`
- Modify: `skill-tree/frontend/package.json`（npm i）

- [ ] **Step 1: 安装依赖**

```bash
cd skill-tree/frontend
npm install marked dompurify highlight.js
npm install -D @types/dompurify
```

- [ ] **Step 2: 写 `Markdown.tsx`**

```tsx
import { useMemo } from 'react'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js/lib/common'

// 配置 marked：代码块用 highlight.js 高亮
marked.setOptions({
  highlight: (code, lang) => {
    if (lang && hljs.getLanguage(lang)) {
      try { return hljs.highlight(code, { language: lang }).value } catch {}
    }
    return hljs.highlightAuto(code).value
  },
})

export function Markdown({ content }: { content: string }) {
  const html = useMemo(() => {
    const raw = marked.parse(content || '', { async: false }) as string
    return DOMPurify.sanitize(raw)
  }, [content])
  return <div className="md" dangerouslySetInnerHTML={{ __html: html }} />
}
```

> 注：`marked` v9+ 的 `highlight` 选项已改为 `marked-highlight` 扩展。若安装的 marked 版本不支持 `highlight` 选项，改用：
> ```tsx
> import { marked } from 'marked'
> import { markedHighlight } from 'marked-highlight'
> import hljs from 'highlight.js/lib/common'
> marked.use(markedHighlight({
>   langPrefix: 'hljs language-',
>   highlight(code, lang) {
>     const language = hljs.getLanguage(lang) ? lang : 'plaintext'
>     return hljs.highlight(code, { language }).value
>   }
> }))
> ```
> 实现时先 `npm ls marked` 看版本，选对应写法，并 `npm install marked-highlight`（若需要）。

- [ ] **Step 3: 类型检查**

Run: `cd skill-tree/frontend && npx tsc --noEmit`
Expected: 无错误（若 marked 类型缺失，加 `// @ts-ignore` 或装 @types/marked）

- [ ] **Step 4: Commit**

```bash
git add skill-tree/frontend/src/Markdown.tsx skill-tree/frontend/package.json skill-tree/frontend/package-lock.json
git commit -m "feat(frontend): Markdown 组件(marked+DOMPurify+highlight.js)"
```

---

## Task 8: App 三栏布局 + 删 FAB

**Files:**
- Modify: `skill-tree/frontend/src/App.tsx`
- Modify: `skill-tree/frontend/src/index.css`

- [ ] **Step 1: App.tsx 三栏 grid + AI 栏常驻**

把 `App` 的 return 结构改为三栏。在 `</main>` 之后、原 FAB 位置，加常驻 AI 栏；删除 `showAi` state 和 FAB 按钮逻辑。

把：
```tsx
      {showAi && (
        <AgentChat onClose={() => setShowAi(false)} />
      )}

      {/* 右下角悬浮 AI 按钮 */}
      {graph && !graph.is_new_user && !showAi && route !== 'setup' && route !== 'settings' && (
        <button className="ai-fab" onClick={() => setShowAi(true)} aria-label="AI 生成">
          <span className="ai-fab-icon">✦</span>
          <span className="ai-fab-pulse" />
        </button>
      )}
```

改为（桌面常驻栏 + 移动 #chat 页面）：

```tsx
      {/* 桌面：右侧常驻 AI 栏（所有路由都在，不随路由切换重建） */}
      {route !== 'setup' && route !== 'settings' && (
        <div className="ai-dock">
          <AgentChat variant="dock" />
        </div>
      )}
```

并删除 `const [showAi, setShowAi] = useState(false)`。新增移动端 `#chat` 路由处理（在 main 区）：

```tsx
        {route === 'chat' && (
          <div className="ai-page">
            <AgentChat variant="page" />
          </div>
        )}
```

路由类型加 `'chat'`，ROUTES 数组加 `'chat'`，移动侧栏导航加 🤖 项。

- [ ] **Step 2: index.css 三栏响应式**

把：
```css
.app { display: grid; grid-template-columns: 256px 1fr; min-height: 100vh; }
```
改为：
```css
.app { display: grid; grid-template-columns: 256px 1fr clamp(320px, 28vw, 440px); min-height: 100vh; }
.ai-dock {
  position: sticky; top: 0; height: 100vh; border-left: 1px solid var(--line-soft);
  background: linear-gradient(180deg, var(--ink-2) 0%, var(--ink) 100%);
  display: flex; flex-direction: column; z-index: 15;
}
.ai-page { padding: 0; height: calc(100vh - 0px); }
```

移动端断点（已有 `@media (max-width: 820px)`）加：三栏退回单栏，`.ai-dock` 隐藏，`.ai-page` 全屏：
```css
@media (max-width: 820px) {
  .app { grid-template-columns: 1fr; }
  .ai-dock { display: none; }
  .ai-page { display: flex; flex-direction: column; height: calc(100vh - 60px); }
}
```

- [ ] **Step 3: 类型检查 + 构建**

Run: `cd skill-tree/frontend && npx tsc --noEmit && npm run build`
Expected: 成功（AgentChat 暂时用旧 props 会报错——下一步 Task 9 重写它，先注释掉 import 让构建过，或先做 Task 9）

> 实务处理：Task 8 和 Task 9 紧耦合，建议一起做。若分任务，Task 8 先把 App 改好但 AgentChat 临时保留旧签名（加 `variant` 可选 prop），Task 9 再重写。

- [ ] **Step 4: Commit**

```bash
git add skill-tree/frontend/src/App.tsx skill-tree/frontend/src/index.css
git commit -m "feat(frontend): 三栏响应式布局 + 删除悬浮 FAB"
```

---

# 阶段四：前端高级（多会话/搜索/引用/流式）

## Task 9: types.ts + api.ts（chat 全套）

**Files:**
- Modify: `skill-tree/frontend/src/types.ts`
- Modify: `skill-tree/frontend/src/api.ts`

- [ ] **Step 1: types.ts 加会话/引用类型**

在文件末尾的 `ChatMessage` 后加：

```typescript
// ── 多会话 ──
export interface ChatSession {
  id: string
  title: string
  created_at: string
  updated_at: string
  messages: ChatMessage[]
}

export interface ChatHistory {
  sessions: ChatSession[]
  current_session_id: string | null
  updated_at?: string
}

export interface SearchHit {
  session_id: string
  session_title: string
  message_index: number
  role: string
  snippet: string
}

export interface RefResolve {
  type: 'node' | 'dir' | 'resource'
  id: string
  name: string
  content: string
}
```

并给 `ChatMessage` 加 `ts?: string` 字段。

- [ ] **Step 2: api.ts 加 chat 端点**

在 `api` 对象内加：

```typescript
  // ── Chat 多会话管理 ──
  chatHistory: () => getJson<ChatHistory>('/api/chat/history'),
  chatSync: (sessions: ChatSession[], currentSessionId: string | null) =>
    postJson<{ ok: boolean }>('/api/chat/sync', { sessions, current_session_id: currentSessionId }),
  chatTitle: (message: string) =>
    postJson<{ title: string }>('/api/chat/title', { message }),
  chatSearch: (q: string) => getJson<{ hits: SearchHit[] }>(`/api/chat/search?q=${encodeURIComponent(q)}`),
  chatExport: (sessionId: string | null) =>
    getJson<any>(`/api/chat/export${sessionId ? `?session_id=${sessionId}` : ''}`),
  chatResolve: (refs: string) => getJson<{ resolved: RefResolve[] }>(`/api/chat/resolve?refs=${encodeURIComponent(refs)}`),
  chatSuggest: (type: string, q: string) =>
    getJson<{ items: { id: string; name: string }[] }>(`/api/chat/suggest?type=${type}&q=${encodeURIComponent(q)}`),
```

顶部 import 补类型：`ChatHistory, ChatSession, SearchHit`。

- [ ] **Step 3: 类型检查**

Run: `cd skill-tree/frontend && npx tsc --noEmit`
Expected: 无错误

- [ ] **Step 4: Commit**

```bash
git add skill-tree/frontend/src/types.ts skill-tree/frontend/src/api.ts
git commit -m "feat(frontend): chat 全套类型 + API(多会话/搜索/导出/引用)"
```

---

## Task 10: ChatToolbar 组件（会话下拉/搜索/导出/折叠）

**Files:**
- Create: `skill-tree/frontend/src/ChatToolbar.tsx`

- [ ] **Step 1: 写 ChatToolbar.tsx**

```tsx
import { useState } from 'react'
import type { ChatSession, SearchHit } from './types'
import { api } from './api'

interface Props {
  sessions: ChatSession[]
  currentId: string | null
  collapsed: boolean
  onToggleCollapse: () => void
  onSelectSession: (id: string) => void
  onNewSession: () => void
  onDeleteSession: (id: string) => void
  onJumpToMessage: (sessionId: string, msgIndex: number) => void
}

export function ChatToolbar(props: Props) {
  const [showSessions, setShowSessions] = useState(false)
  const [showSearch, setShowSearch] = useState(false)
  const [searchQ, setSearchQ] = useState('')
  const [hits, setHits] = useState<SearchHit[]>([])
  const [confirmDel, setConfirmDel] = useState<string | null>(null)

  const current = props.sessions.find(s => s.id === props.currentId)
  const doSearch = async () => {
    if (!searchQ.trim()) return
    const r = await api.chatSearch(searchQ)
    setHits(r.hits)
  }

  const doExport = async () => {
    const data = await api.chatExport(props.currentId)
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${current?.title || '对话'}.json`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  if (props.collapsed) {
    return (
      <div className="chat-toolbar collapsed">
        <button className="tbtn" onClick={props.onToggleCollapse} title="展开">✦</button>
      </div>
    )
  }

  return (
    <div className="chat-toolbar">
      <button className="tbtn" onClick={() => setShowSessions(v => !v)} title="会话列表">
        ▾ {current?.title || '新会话'}
      </button>
      <div className="tbtn-group">
        <button className="tbtn ico" onClick={() => setShowSearch(v => !v)} title="搜索">🔍</button>
        <button className="tbtn ico" onClick={doExport} title="导出 JSON">⤓</button>
        <button className="tbtn ico" onClick={props.onToggleCollapse} title="折叠">▸</button>
      </div>

      {showSessions && (
        <div className="dropdown">
          <button className="dd-item new" onClick={() => { props.onNewSession(); setShowSessions(false) }}>+ 新会话</button>
          {props.sessions.map(s => (
            <div key={s.id} className={`dd-item ${s.id === props.currentId ? 'active' : ''}`}>
              <span onClick={() => { props.onSelectSession(s.id); setShowSessions(false) }}>{s.title}</span>
              <button className="dd-del" onClick={() => setConfirmDel(s.id)}>✕</button>
            </div>
          ))}
        </div>
      )}

      {showSearch && (
        <div className="search-box">
          <input value={searchQ} onChange={e => setSearchQ(e.target.value)}
                 onKeyDown={e => e.key === 'Enter' && doSearch()} placeholder="搜索所有会话…" />
          <div className="search-hits">
            {hits.map((h, i) => (
              <div key={i} className="hit" onClick={() => { props.onJumpToMessage(h.session_id, h.message_index); setShowSearch(false) }}>
                <div className="hit-title">{h.session_title}</div>
                <div className="hit-snip">{h.snippet}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {confirmDel && (
        <div className="confirm-mask" onClick={() => setConfirmDel(null)}>
          <div className="confirm-box" onClick={e => e.stopPropagation()}>
            <p>删除此会话？不可恢复。</p>
            <button className="aibtn ghost" onClick={() => setConfirmDel(null)}>取消</button>
            <button className="aibtn solid" onClick={() => { props.onDeleteSession(confirmDel); setConfirmDel(null) }}>删除</button>
          </div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add skill-tree/frontend/src/ChatToolbar.tsx
git commit -m "feat(frontend): ChatToolbar(会话下拉/搜索/导出/折叠/删除确认)"
```

---

## Task 11: MentionInput 组件（#/@/$ 补全）

**Files:**
- Create: `skill-tree/frontend/src/MentionInput.tsx`

- [ ] **Step 1: 写 MentionInput.tsx**

```tsx
import { useState, useRef, useEffect } from 'react'
import { api } from './api'

interface Props {
  value: string
  onChange: (v: string) => void
  onSend: () => void
  onCommand?: (cmd: string) => void   // 处理 /new 等命令
  placeholder?: string
}

const SYM_MAP: Record<string, string> = { '#': 'node', '@': 'resource', '$': 'dir' }
const SYM_LABEL: Record<string, string> = { '#': '节点', '@': '资源', '$': '方向' }

export function MentionInput({ value, onChange, onSend, onCommand, placeholder }: Props) {
  const [suggestions, setSuggestions] = useState<{ id: string; name: string }[]>([])
  const [activeSym, setActiveSym] = useState<string | null>(null)
  const [prefix, setPrefix] = useState('')
  const [selIdx, setSelIdx] = useState(0)
  const debounceRef = useRef<number>(0)

  // 检测光标前的 #/@/$ + 前缀
  useEffect(() => {
    const m = value.match(/([#@$])([^\s#@$]*)$/)
    if (m) {
      const sym = m[1], pre = m[2]
      setActiveSym(sym)
      setPrefix(pre)
      window.clearTimeout(debounceRef.current)
      debounceRef.current = window.setTimeout(async () => {
        const r = await api.chatSuggest(SYM_MAP[sym], pre)
        setSuggestions(r.items)
        setSelIdx(0)
      }, 150)
    } else {
      setActiveSym(null)
      setSuggestions([])
    }
  }, [value])

  const insertSuggestion = (item: { id: string; name: string }) => {
    // 把光标前的 #prefix 替换为 #id（用 id 更稳定）
    const newValue = value.replace(/([#@$])[^\s#@$]*$/, `$1${item.id} `)
    onChange(newValue)
    setActiveSym(null)
    setSuggestions([])
  }

  const handleKey = (e: React.KeyboardEvent) => {
    // 补全弹层导航
    if (activeSym && suggestions.length > 0) {
      if (e.key === 'ArrowDown') { e.preventDefault(); setSelIdx(i => (i + 1) % suggestions.length); return }
      if (e.key === 'ArrowUp') { e.preventDefault(); setSelIdx(i => (i - 1 + suggestions.length) % suggestions.length); return }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault(); insertSuggestion(suggestions[selIdx]); return
      }
      if (e.key === 'Escape') { setActiveSym(null); setSuggestions([]); return }
    }
    // 发送 / 命令
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      const trimmed = value.trim()
      if (trimmed.startsWith('/') && onCommand) {
        onCommand(trimmed)
        onChange('')
      } else {
        onSend()
      }
    }
  }

  return (
    <div className="mention-wrap">
      {activeSym && suggestions.length > 0 && (
        <div className="mention-pop">
          <div className="mention-pop-title">{SYM_LABEL[activeSym]}</div>
          {suggestions.map((s, i) => (
            <div key={s.id} className={`mention-item ${i === selIdx ? 'active' : ''}`}
                 onClick={() => insertSuggestion(s)}>{s.name} <span className="mention-id">{s.id}</span></div>
          ))}
        </div>
      )}
      <textarea
        className="ai-textarea"
        value={value}
        onChange={e => onChange(e.target.value)}
        onKeyDown={handleKey}
        rows={2}
        placeholder={placeholder || '问我… 用 #节点 @资源 $方向 引用，/new 开新会话'}
      />
      <button className="aibtn solid" onClick={onSend} disabled={!value.trim()}>发送 ▸</button>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add skill-tree/frontend/src/MentionInput.tsx
git commit -m "feat(frontend): MentionInput(#/@/$ 补全 + /new 命令)"
```

---

## Task 12: AgentChat 重写（响应式 + 多会话 + 流式 + 引用渲染）

**Files:**
- Rewrite: `skill-tree/frontend/src/AgentChat.tsx`
- Modify: `skill-tree/frontend/src/ChatMessage.tsx`

- [ ] **Step 1: ChatMessage.tsx 加流式光标 + Markdown + 引用 chip**

```tsx
import type { ChatMessage as Msg, AgentEvent } from './types'
import { Markdown } from './Markdown'

export function ChatMessageView({ msg, streaming }: { msg: Msg; streaming?: boolean }) {
  if (msg.role === 'user') {
    return <div className="chat-msg user">{renderRefs(msg.content)}</div>
  }
  return (
    <div className="chat-msg assistant">
      {msg.events?.map((ev, i) => <EventView key={i} ev={ev} />)}
      {msg.content && (
        streaming
          ? <div className="chat-answer streaming">{msg.content}<span className="cursor">▌</span></div>
          : <div className="chat-answer"><Markdown content={msg.content} /></div>
      )}
    </div>
  )
}

// 把 #id @id $id 渲染成玉青 chip（在 Markdown 之外，纯文本消息用）
function renderRefs(text: string) {
  const parts = text.split(/([#@$][^\s#@$，。、]+)/g)
  return parts.map((p, i) => {
    const m = p.match(/^([#@$])(.+)/)
    if (m) return <span key={i} className="ref-chip">{m[1]}{m[2]}</span>
    return <span key={i}>{p}</span>
  })
}

function EventView({ ev }: { ev: AgentEvent }) {
  switch (ev.type) {
    case 'thinking': return <div className="chat-thinking">💭 {ev.content}</div>
    case 'tool_call': return <div className="chat-tool">🔧 调用 {ev.action}</div>
    case 'tool_result': return <div className="chat-toolres">{ev.content}</div>
    case 'doc_card': return null
    default: return null
  }
}
```

- [ ] **Step 2: AgentChat.tsx 重写（响应式 + 多会话状态 + 流式 + 双写）**

```tsx
import { useState, useRef, useEffect, useCallback } from 'react'
import { api, getUserId } from './api'
import type { ChatMessage as Msg, ChatSession, AgentEvent } from './types'
import { ChatMessageView } from './ChatMessage'
import { ChatToolbar } from './ChatToolbar'
import { MentionInput } from './MentionInput'
import { DocCard } from './DocCard'

interface Props {
  variant?: 'dock' | 'page'
}

const CACHE_KEY = (uid: string) => `chat_${uid}`

export function AgentChat({ variant = 'dock' }: Props) {
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [currentId, setCurrentId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  const uid = getUserId()
  const current = sessions.find(s => s.id === currentId)

  // 首屏加载：localStorage 缓存秒开 → 后端校正
  useEffect(() => {
    const cached = localStorage.getItem(CACHE_KEY(uid))
    if (cached) {
      try {
        const c = JSON.parse(cached)
        setSessions(c.sessions || []); setCurrentId(c.current_session_id)
      } catch {}
    }
    api.chatHistory().then(h => {
      setSessions(h.sessions); setCurrentId(h.current_session_id)
      if (h.sessions.length === 0) {
        // 首次：创建一个空会话
        newSession()
      }
    }).catch(() => {})
  }, [uid])

  // 双写：sessions 变化时同步后端 + 缓存
  const sync = useCallback((newSessions: ChatSession[], newCurrent: string | null) => {
    localStorage.setItem(CACHE_KEY(uid), JSON.stringify({ sessions: newSessions, current_session_id: newCurrent }))
    api.chatSync(newSessions, newCurrent).catch(() => {})
  }, [uid])

  const newSession = useCallback(() => {
    const sid = `s_${Date.now()}`
    const s: ChatSession = {
      id: sid, title: '新会话',
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(), messages: [],
    }
    setSessions(prev => {
      const next = [...prev, s]
      sync(next, sid)
      return next
    })
    setCurrentId(sid)
  }, [sync])

  const updateCurrent = (updater: (s: ChatSession) => ChatSession) => {
    setSessions(prev => {
      const next = prev.map(s => s.id === currentId ? updater(s) : s)
      sync(next, currentId)
      return next
    })
  }

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [current?.messages])

  const send = async () => {
    const text = input.trim()
    if (!text || busy || !currentId) return
    setInput('')
    const userMsg: Msg = { role: 'user', content: text, ts: new Date().toISOString() }
    const asstMsg: Msg = { role: 'assistant', content: '', events: [], ts: new Date().toISOString() }
    updateCurrent(s => ({ ...s, messages: [...s.messages, userMsg, asstMsg] }))
    setBusy(true); setStreaming(true)

    // 异步生成标题（首条消息后）
    if (current && current.messages.length === 0) {
      api.chatTitle(text).then(r => {
        updateCurrent(s => ({ ...s, title: r.title }))
      }).catch(() => {})
    }

    try {
      await api.agentChatStream(text, (ev: AgentEvent) => {
        setSessions(prev => {
          const next = prev.map(s => {
            if (s.id !== currentId) return s
            const msgs = [...s.messages]
            const last = { ...msgs[msgs.length - 1] }
            if (ev.type === 'delta') {
              last.content = (last.content || '') + ev.content
            } else if (ev.type === 'final_done') {
              // 流式结束，content 已完整
            } else if (ev.type === 'final_answer') {
              last.content = ev.content   // 降级兜底
            } else {
              last.events = [...(last.events || []), ev]
            }
            msgs[msgs.length - 1] = last
            return { ...s, messages: msgs }
          })
          return next
        })
      })
      // 流式结束后把完整会话同步后端
      setSessions(prev => { sync(prev, currentId); return prev })
    } catch (e: any) {
      updateCurrent(s => {
        const msgs = [...s.messages]
        msgs[msgs.length - 1] = { ...msgs[msgs.length - 1], content: '⚠ ' + String(e.message || e) }
        return { ...s, messages: msgs }
      })
    }
    setBusy(false); setStreaming(false)
  }

  const handleCommand = (cmd: string) => {
    if (cmd === '/new') newSession()
  }

  const deleteSession = (id: string) => {
    setSessions(prev => {
      const next = prev.filter(s => s.id !== id)
      const newCurrent = next.length ? (id === currentId ? next[0].id : currentId) : null
      sync(next, newCurrent)
      return next
    })
    if (id === currentId) setCurrentId(sessions.find(s => s.id !== id)?.id || null)
  }

  const jumpToMessage = (sessionId: string, _msgIndex: number) => {
    setCurrentId(sessionId)
    setTimeout(() => {
      const el = scrollRef.current
      if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    }, 100)
  }

  return (
    <div className={`agent-chat ${variant}`}>
      <ChatToolbar
        sessions={sessions} currentId={currentId} collapsed={collapsed}
        onToggleCollapse={() => setCollapsed(v => !v)}
        onSelectSession={setCurrentId}
        onNewSession={newSession}
        onDeleteSession={deleteSession}
        onJumpToMessage={jumpToMessage}
      />
      {!collapsed && (
        <>
          <div className="chat-msgs" ref={scrollRef}>
            {current?.messages.length === 0 && <div className="chat-empty">问我学到哪了、下一步学啥…<br/>用 #节点 @资源 $方向 引用，/new 开新会话</div>}
            {current?.messages.map((m, i) => (
              <div key={i}>
                <ChatMessageView msg={m} streaming={streaming && i === (current.messages.length - 1) && m.role === 'assistant'} />
                {m.events?.some(e => e.type === 'doc_card') && (
                  <DocCard content={(m.events!.find(e => e.type === 'doc_card') as any)?.content || ''} onPublished={() => {}} />
                )}
              </div>
            ))}
          </div>
          <MentionInput value={input} onChange={setInput} onSend={send}
                        onCommand={handleCommand} placeholder="问我… #节点 @资源 $方向 /new" />
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 3: index.css 补全 AI 栏/工具条/mention/md 样式**

追加到 `index.css`（玉青宝石工坊风格，复用既有变量）：

```css
/* ─── AI 对话区 ─── */
.agent-chat { display: flex; flex-direction: column; height: 100%; }
.agent-chat.dock { height: 100vh; }
.chat-toolbar { display: flex; align-items: center; justify-content: space-between;
  padding: 12px 14px; border-bottom: 1px solid var(--line-soft); position: relative; gap: 8px; }
.chat-toolbar.collapsed { flex-direction: column; padding: 8px; }
.tbtn { background: transparent; border: 1px solid var(--line); color: var(--fg-dim);
  border-radius: 8px; padding: 6px 10px; cursor: pointer; font-size: 13px; }
.tbtn:hover { background: var(--moss); color: var(--fg); }
.tbtn.ico { padding: 6px 8px; }
.tbtn-group { display: flex; gap: 4px; }
.dropdown { position: absolute; top: 100%; left: 14px; right: 14px; background: var(--moss-2);
  border: 1px solid var(--glass-border); border-radius: 10px; padding: 6px; z-index: 30; max-height: 300px; overflow-y: auto; }
.dd-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 10px;
  border-radius: 6px; cursor: pointer; color: var(--fg-dim); font-size: 13px; }
.dd-item:hover, .dd-item.active { background: var(--jade-soft); color: var(--fg); }
.dd-item.new { color: var(--jade); border-bottom: 1px solid var(--line-soft); margin-bottom: 4px; }
.dd-del { background: transparent; border: none; color: var(--fg-faint); cursor: pointer; opacity: 0; }
.dd-item:hover .dd-del { opacity: 1; }
.dd-del:hover { color: var(--rose); }
.search-box { position: absolute; top: 100%; left: 14px; right: 14px; background: var(--moss-2);
  border: 1px solid var(--glass-border); border-radius: 10px; padding: 8px; z-index: 30; }
.search-box input { width: 100%; background: var(--ink); border: 1px solid var(--line);
  border-radius: 6px; padding: 6px 8px; color: var(--fg); }
.search-hits { margin-top: 6px; max-height: 240px; overflow-y: auto; }
.hit { padding: 8px; border-radius: 6px; cursor: pointer; }
.hit:hover { background: var(--jade-soft); }
.hit-title { font-size: 12px; color: var(--jade); }
.hit-snip { font-size: 12px; color: var(--fg-dim); }
.confirm-mask { position: fixed; inset: 0; background: rgba(0,0,0,.5); display: flex;
  align-items: center; justify-content: center; z-index: 50; }
.confirm-box { background: var(--moss-2); border: 1px solid var(--glass-border);
  border-radius: 12px; padding: 20px; text-align: center; }
.confirm-box p { margin-bottom: 14px; color: var(--fg); }
.chat-msgs { flex: 1; overflow-y: auto; padding: 16px 14px; }
.chat-empty { text-align: center; color: var(--fg-faint); padding: 40px 20px; font-size: 13px; line-height: 1.8; }
.chat-msg { margin-bottom: 14px; line-height: 1.6; }
.chat-msg.user { background: var(--moss); border-radius: 12px 12px 4px 12px; padding: 10px 14px;
  margin-left: 40px; color: var(--fg); }
.chat-msg.assistant { color: var(--fg); }
.chat-answer.streaming { color: var(--fg-dim); }
.cursor { color: var(--jade); animation: blink 1s steps(2) infinite; }
@keyframes blink { 50% { opacity: 0; } }
.chat-thinking { font-size: 12px; color: var(--fg-faint); margin: 4px 0; }
.chat-tool { font-size: 12px; color: var(--jade); margin: 2px 0; }
.chat-toolres { font-size: 12px; color: var(--fg-dim); background: var(--ink-2);
  border-left: 2px solid var(--bark); padding: 6px 10px; border-radius: 4px; margin: 4px 0; }
.ref-chip { color: var(--jade); background: var(--jade-soft); padding: 1px 6px;
  border-radius: 8px; font-size: 0.9em; cursor: pointer; }
.mention-wrap { position: relative; padding: 10px 12px; border-top: 1px solid var(--line-soft); }
.mention-pop { position: absolute; bottom: 100%; left: 12px; right: 12px; background: var(--moss-2);
  border: 1px solid var(--glass-border); border-radius: 8px; padding: 4px; max-height: 200px; overflow-y: auto; z-index: 30; }
.mention-pop-title { font-size: 11px; color: var(--jade); padding: 4px 8px; }
.mention-item { padding: 6px 10px; border-radius: 6px; cursor: pointer; font-size: 13px; }
.mention-item.active, .mention-item:hover { background: var(--jade-soft); }
.mention-id { color: var(--fg-faint); font-size: 11px; margin-left: 8px; }

/* ─── Markdown 渲染(玉青宝石工坊) ─── */
.md { line-height: 1.7; }
.md h1, .md h2, .md h3 { font-family: 'Fraunces', 'Noto Serif SC', serif; color: var(--jade);
  border-left: 3px solid var(--jade); padding-left: 10px; margin: 14px 0 8px; }
.md h1 { font-size: 18px; } .md h2 { font-size: 16px; } .md h3 { font-size: 14px; }
.md p { margin: 8px 0; }
.md code { font-family: 'JetBrains Mono', monospace; background: var(--moss-2);
  color: var(--jade); padding: 1px 5px; border-radius: 4px; font-size: 0.9em; }
.md pre { background: var(--ink-2); border: 1px solid var(--glass-border);
  border-left: 3px solid var(--jade); border-radius: 6px; padding: 12px; overflow-x: auto; margin: 10px 0; }
.md pre code { background: transparent; color: var(--fg); padding: 0; }
.md blockquote { border-left: 3px solid var(--jade); color: var(--fg-dim);
  font-style: italic; padding-left: 12px; margin: 8px 0; }
.md ul { padding-left: 20px; } .md li { margin: 4px 0; }
.md ul li::marker { color: var(--jade); }
.md table { border-collapse: collapse; width: 100%; margin: 10px 0; }
.md th, .md td { border: 1px solid var(--line); padding: 6px 10px; text-align: left; }
.md th { background: var(--moss-2); color: var(--jade); }
.md a { color: var(--jade); text-decoration: underline; }
.md strong { color: var(--gold); }
```

- [ ] **Step 4: 类型检查 + 构建**

Run: `cd skill-tree/frontend && npx tsc --noEmit && npm run build`
Expected: 成功

- [ ] **Step 5: Commit**

```bash
git add skill-tree/frontend/src/AgentChat.tsx skill-tree/frontend/src/ChatMessage.tsx skill-tree/frontend/src/index.css
git commit -m "feat(frontend): AgentChat 重写(响应式+多会话+流式+引用渲染)"
```

---

## 全量回归

- [ ] **Step 1: 后端全量测试**

Run: `cd skill-tree/backend && python -m pytest tests/ -q`
Expected: 全绿（含 chat_store 15 个 + 原有）

- [ ] **Step 2: 前端构建**

Run: `cd skill-tree/frontend && npm run build`
Expected: 成功

- [ ] **Step 3: 端到端冒烟（手动）**

1. 起 docker-compose 或前后端分别起
2. 打开 http://localhost:5173 → 右侧应有常驻 AI 栏
3. 输入 `你好` → 流式逐字出现 + 光标 ▌ + 完成后 Markdown 渲染
4. 输入 `/new` → 新会话，顶部下拉能切回旧的
5. 输入 `#deep` → 弹节点补全，选中插入 chip
6. 搜索框搜关键词 → 跨会话命中
7. 导出按钮 → 下载 JSON
8. 删除会话 → 二次确认
9. 缩窗到 <820px → AI 栏消失，侧栏出现 🤖，点进全屏 chat

---

## Self-Review（计划自检）

**1. Spec 覆盖：**
- §2 三栏布局 → Task 8 ✓
- §4 多会话（/new + 下拉 + LLM标题 + 删除确认）→ Task 1(store) + Task 4(title端点) + Task 10(toolbar) + Task 12(状态) ✓
- §5 搜索导出 → Task 2 + Task 4(端点) + Task 10(UI) ✓
- §6 符号引用（mention + 后端解析注入）→ Task 3(resolve/suggest) + Task 5(loop注入) + Task 11(MentionInput) + Task 12(chip渲染) ✓
- §7 全链路流式 → Task 6(loop delta) + Task 12(前端流式渲染) ✓
- §8 双写记忆 → Task 1(replace_all) + Task 4(sync端点) + Task 12(localStorage+sync) ✓
- §9 Markdown → Task 7 ✓
- §3 路由/删FAB → Task 8 ✓

**2. 占位符扫描：** 无 TBD/TODO，所有步骤含完整代码。Task 4 的 export 端点签名笔误已在 task 内附纠正说明。✓

**3. 类型一致性：**
- `ChatSession {id,title,created_at,updated_at,messages}` 前后端一致 ✓
- `ChatStore.new_session/append_message/search/export/resolve_refs/suggest` 方法名一致 ✓
- SSE 事件 `delta`/`final_done`/`final_answer`(降级) 前后端一致 ✓
- AgentChat `variant: 'dock'|'page'` 与 App.tsx Task 8 使用一致 ✓

**GAP 注意**：Task 6 流式改造后，现有 `test_loop_*` 测试用 FakeChat——需确认 FakeChat 的 stream 分支返回 `{type:delta}` 迭代器（T1 的 fakes.py 已实现），`_stream_final` 能消费它。若现有测试因 final_answer→delta 变更而失败，需在 Task 6 调整断言（允许事件序列含 delta）。已在 Task 6 Step 3 标注"确认不破"。
