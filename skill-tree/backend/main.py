"""main.py — FastAPI 后端（单用户 + AI 生成）。

数据全部存放在 DATA_ROOT 下（单用户）。DATA_ROOT 默认指向
data/users/default，可通过环境变量 DATA_ROOT 覆盖（测试与桌面打包依赖此点）。

API:
  GET  /api/graph          合并去重 + 布局 + 掌握度 + 成就 + 总览
  PATCH /api/task          勾选/取消勾选任务(写回 JSON)
  GET  /api/profile        个人信息
  GET  /api/templates      简历模板
  GET  /api/fruits         果实(简历成品)
  GET/PUT /api/llm-config  读/存 LLM 配置
  POST /api/llm-config/test  测连通
  POST /api/ai/generate-tree|direction|node   AI 生成
"""
from __future__ import annotations
import glob
import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import layout as layout_mod
import progress as progress_mod
import ai as ai_mod
import agent.loop as agent_loop
import agent.session as agent_session
import agent.tool_runtime as agent_tool
from rag.retriever import Retriever
from larkpub import publish_doc
from chat_store import ChatStore
from fastapi.responses import StreamingResponse

HERE = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ.get("DATA_ROOT", HERE.parent / "data" / "users" / "default"))
RESUME_DIR = Path(os.environ.get("RESUME_DIR", HERE.parent.parent / "resume"))
TEMPLATES_DIR = RESUME_DIR / "templates"
PROFILES_DIR = RESUME_DIR / "profiles"
BUILD_DIR = RESUME_DIR / "build"
# projects/ 已移出本仓库到父目录(与 Resume 同级)。env 可覆盖。
PROJECTS_DIR = Path(os.environ.get("PROJECTS_DIR", HERE.parent.parent.parent / "projects"))

app = FastAPI(title="Skill Tree API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
if PROJECTS_DIR.exists():
    app.mount("/projects", StaticFiles(directory=str(PROJECTS_DIR)), name="projects")
if RESUME_DIR.exists():
    app.mount("/resume", StaticFiles(directory=str(RESUME_DIR)), name="resume")

# ── Agent 会话存储 + RAG 索引目录 ──
SESSIONS = agent_session.SessionStore(ttl=1800)


def rag_index_dir() -> Path:
    """RAG 索引目录（DATA_ROOT/rag_index）。"""
    d = DATA_ROOT / "rag_index"
    d.mkdir(parents=True, exist_ok=True)
    return d


def chat_store_path() -> Path:
    return DATA_ROOT / "chat_history.json"


def chat_store() -> ChatStore:
    return ChatStore(chat_store_path())


def _load_json(p: Path) -> Any:
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(p: Path, data: Any) -> None:
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_trees(data_dir: Path) -> list[dict]:
    trees = []
    for p in glob.glob(str(data_dir / "*.json")):
        if os.path.basename(p) in ("achievements.json", "profile.json", "llm_config.json", "chat_history.json"):
            continue
        trees.append(_load_json(Path(p)))
    trees.sort(key=lambda t: (t.get("order", 99), t.get("tree_id", "")))
    return trees


def load_achievements(data_dir: Path) -> dict:
    p = data_dir / "achievements.json"
    return _load_json(p) if p.exists() else {"achievements": []}


# ─────────────────────────── 图谱 ───────────────────────────
@app.get("/api/graph")
def get_graph() -> dict:
    dd = DATA_ROOT
    trees = load_trees(dd)
    achievements = load_achievements(dd)
    lay = layout_mod.compute_layout(trees)
    raw_nodes: dict[str, dict] = {}
    for t in trees:
        for b in t.get("branches", []):
            for n in b.get("nodes", []):
                if n["id"] not in raw_nodes:
                    raw_nodes[n["id"]] = n
    for n in lay["nodes"]:
        raw = raw_nodes.get(n["id"], {})
        m, tot, pct = progress_mod.node_mastery(raw)
        n["mastered"] = m
        n["total_points"] = tot
        n["pct"] = pct
        n["state"] = progress_mod.node_status(raw)
    ach_results = progress_mod.evaluate_achievements(trees, achievements)
    tot_m, tot_t = 0, 0
    for t in trees:
        m, tt, _ = progress_mod.tree_progress(t.get("branches", []))
        tot_m += m
        tot_t += tt
    overview = {
        "overall_pct": 0 if tot_t == 0 else round(tot_m / tot_t * 100),
        "mastered_points": tot_m,
        "total_points": tot_t,
        "done_nodes": sum(1 for n in lay["nodes"] if n["state"] == "done"),
        "total_nodes": len(lay["nodes"]),
        "achievements_unlocked": sum(1 for _, ok in ach_results if ok),
        "achievements_total": len(ach_results),
        "tree_count": len(trees),
    }
    return {
        "nodes": lay["nodes"],
        "edges": lay["edges"],
        "canvas": lay["canvas"],
        "constants": lay["constants"],
        "dir_order": lay["dir_order"],
        "achievements": [{"def": a, "unlocked": ok} for a, ok in ach_results],
        "overview": overview,
        "is_new_user": len(trees) == 0,
    }


# ─────────────────────────── 勾选 ───────────────────────────
class TaskPatch(BaseModel):
    tree_id: str
    node_id: str
    task_id: str
    done: bool
    is_verify: bool = False


def _find_tree_file(data_dir: Path, tree_id: str) -> Path | None:
    for p in glob.glob(str(data_dir / "*.json")):
        if os.path.basename(p) in ("achievements.json", "profile.json", "llm_config.json", "chat_history.json"):
            continue
        if _load_json(Path(p)).get("tree_id") == tree_id:
            return Path(p)
    return None


def _apply_done(tree: dict, node_id: str, task_id: str, done: bool) -> bool:
    for b in tree.get("branches", []):
        for n in b.get("nodes", []):
            if n["id"] != node_id:
                continue
            for tk in n.get("tasks", []):
                if tk["id"] == task_id:
                    tk["done"] = done
                    return True
                for v in tk.get("verify", []):
                    if v["id"] == task_id:
                        v["done"] = done
                        return True
            for v in n.get("verify", []):
                if v["id"] == task_id:
                    v["done"] = done
                    return True
    return False


@app.patch("/api/task")
def patch_task(patch: TaskPatch) -> dict:
    dd = DATA_ROOT
    path = _find_tree_file(dd, patch.tree_id)
    if path is None:
        raise HTTPException(404, f"tree not found: {patch.tree_id}")
    full = _load_json(path)
    if not _apply_done(full, patch.node_id, patch.task_id, patch.done):
        raise HTTPException(404, f"task not found: {patch.tree_id}/{patch.node_id}/{patch.task_id}")
    _save_json(path, full)
    SESSIONS.invalidate_snapshot("default", "graph")
    return get_graph()


# ─────────────────────────── LLM 配置 ───────────────────────────
class LlmConfig(BaseModel):
    provider: str = ""
    base_url: str = ""
    api_key: str = ""
    model: str = ""


def llm_config_path() -> Path:
    return DATA_ROOT / "llm_config.json"


@app.get("/api/llm-config")
def get_llm_config() -> dict:
    p = llm_config_path()
    if not p.exists():
        return {"provider": "", "base_url": "", "api_key": "", "model": "", "configured": False}
    cfg = _load_json(p)
    cfg["configured"] = bool(cfg.get("api_key") and cfg.get("base_url"))
    return cfg


@app.put("/api/llm-config")
def put_llm_config(cfg: LlmConfig) -> dict:
    p = llm_config_path()
    data = cfg.model_dump()
    _save_json(p, data)
    return {"saved": True, "configured": bool(data["api_key"] and data["base_url"])}


@app.post("/api/llm-config/test")
def test_llm_config(cfg: LlmConfig) -> dict:
    ok, msg = ai_mod.test_connection(cfg.base_url, cfg.api_key, cfg.model)
    return {"ok": ok, "message": msg}


@app.post("/api/llm-config/models")
def list_models_api(cfg: LlmConfig) -> dict:
    """根据 base_url + api_key 拉取可用模型列表（OpenAI 兼容 /models）。"""
    try:
        models = ai_mod.list_models(cfg.base_url, cfg.api_key)
        return {"ok": True, "models": models}
    except Exception as e:
        return {"ok": False, "models": [], "error": str(e)}


@app.get("/api/providers")
def providers() -> list[dict]:
    return ai_mod.PROVIDER_PRESETS


# ─────────────────────────── AI 生成 ───────────────────────────
class GenTreeReq(BaseModel):
    jd: str
    extra: str = ""           # 额外说明(已有方向/偏好)


class GenDirectionReq(BaseModel):
    description: str
    existing_ids: list[str] = []   # 现有 node id，供 depends_on 引用


class GenNodeReq(BaseModel):
    description: str
    node_id: str = ""         # 要补充的节点(补子任务/验收); 空则新建节点
    existing_ids: list[str] = []


@app.post("/api/ai/generate-tree")
def gen_tree(req: GenTreeReq) -> dict:
    p = llm_config_path()
    cfg = _load_json(p) if p.exists() else {}
    if not cfg.get("api_key"):
        raise HTTPException(400, "请先配置 LLM (api_key)")
    try:
        result = ai_mod.generate_tree(cfg, req.jd, req.extra)
        return {"ok": True, "data": result}
    except Exception as e:
        raise HTTPException(500, f"生成失败: {e}")


@app.post("/api/ai/generate-direction")
def gen_direction(req: GenDirectionReq) -> dict:
    p = llm_config_path()
    cfg = _load_json(p) if p.exists() else {}
    if not cfg.get("api_key"):
        raise HTTPException(400, "请先配置 LLM")
    try:
        result = ai_mod.generate_direction(cfg, req.description, req.existing_ids)
        return {"ok": True, "data": result}
    except Exception as e:
        raise HTTPException(500, f"生成失败: {e}")


@app.post("/api/ai/generate-node")
def gen_node(req: GenNodeReq) -> dict:
    p = llm_config_path()
    cfg = _load_json(p) if p.exists() else {}
    if not cfg.get("api_key"):
        raise HTTPException(400, "请先配置 LLM")
    try:
        result = ai_mod.generate_node(cfg, req.description, req.node_id, req.existing_ids)
        return {"ok": True, "data": result}
    except Exception as e:
        raise HTTPException(500, f"生成失败: {e}")


@app.post("/api/ai/apply-tree")
def apply_tree(payload: dict) -> dict:
    """把 AI 生成的树写回 DATA_ROOT（覆盖现有方向）。payload: {trees:[...], profile:{}}"""
    dd = DATA_ROOT
    trees = payload.get("trees", [])
    for t in trees:
        fname = f"{t.get('tree_id','gen')}.json"
        _save_json(dd / fname, t)
    if payload.get("profile"):
        _save_json(dd / "profile.json", payload["profile"])
    SESSIONS.invalidate_snapshot("default", "graph")
    return {"ok": True, "written": len(trees)}


@app.post("/api/ai/apply-direction")
def apply_direction(payload: dict) -> dict:
    """把 AI 生成的单方向作为新文件写入。payload: {tree: {...}}"""
    dd = DATA_ROOT
    t = payload.get("tree", {})
    if t:
        fname = f"{t.get('tree_id','gen_dir')}.json"
        _save_json(dd / fname, t)
    SESSIONS.invalidate_snapshot("default", "graph")
    return {"ok": True}


def _apply_node_to_tree(tree: dict, node: dict, branch_id: str | None = None) -> bool:
    """把 node 插入 tree 的指定 branch(空则第一个 branch)。同 id 去重。返回是否插入。"""
    branches = tree.get("branches", [])
    target = None
    for b in branches:
        if branch_id and b.get("id") == branch_id:
            target = b
            break
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


class ApplyNodeReq(BaseModel):
    tree_id: str
    node: dict
    branch_id: str | None = None


@app.post("/api/ai/apply-node")
def apply_node(req: ApplyNodeReq) -> dict:
    """把 node_proposal 确认的节点写入指定 tree 文件。"""
    dd = DATA_ROOT
    path = _find_tree_file(dd, req.tree_id)
    if path is None:
        raise HTTPException(404, f"tree not found: {req.tree_id}")
    tree = _load_json(path)
    if not _apply_node_to_tree(tree, req.node, req.branch_id):
        raise HTTPException(400, "插入失败:无 branch 或 id 已存在")
    _save_json(path, tree)
    SESSIONS.invalidate_snapshot("default", "graph")
    return {"ok": True, "written": True}


class ApplyTasksReq(BaseModel):
    tree_id: str
    node_id: str
    tasks: list


@app.post("/api/ai/apply-tasks")
def apply_tasks(req: ApplyTasksReq) -> dict:
    """把 node_proposal 确认的补充 tasks 追加到指定 node。"""
    dd = DATA_ROOT
    path = _find_tree_file(dd, req.tree_id)
    if path is None:
        raise HTTPException(404, f"tree not found: {req.tree_id}")
    tree = _load_json(path)
    if not _apply_tasks_to_node(tree, req.node_id, req.tasks):
        raise HTTPException(404, f"node not found: {req.node_id}")
    _save_json(path, tree)
    SESSIONS.invalidate_snapshot("default", "graph")
    return {"ok": True}


# ─────────────────────────── Agent 对话(SSE) ───────────────────────────
class AgentChatReq(BaseModel):
    message: str
    history: list = []


def _build_ctx() -> tuple[agent_tool.Context, dict]:
    """组装工具执行上下文：当前图谱(layout+掌握度) + 简历 + retriever + 勾选回调。"""
    # agent 包内 Context/SessionStore 仍按 uid 做缓存键，单机应用固定用 "default"。
    uid = "default"
    dd = DATA_ROOT
    cached = SESSIONS.get_snapshot(uid, "graph")
    if cached is not None:
        graph = cached["graph"]
        trees = cached["trees"]
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
    cfg_p = llm_config_path()
    cfg = _load_json(cfg_p) if cfg_p.exists() else {}
    retriever = Retriever(index_dir=rag_index_dir(), cfg=cfg)

    def on_toggle(tree_id, node_id, task_id, done):
        path = _find_tree_file(dd, tree_id)
        if path is None:
            return False
        full = _load_json(path)
        if _apply_done(full, node_id, task_id, done):
            _save_json(path, full)
            SESSIONS.invalidate_snapshot(uid, "graph")
            return True
        return False

    ctx = agent_tool.Context(uid=uid, graph=graph, resume=resume,
                             retriever=retriever, rag_index_dir=rag_index_dir(),
                             trees=trees, cfg=cfg)
    ctx.on_toggle = on_toggle  # type: ignore[attr-defined]
    return ctx, cfg


@app.post("/api/agent/chat")
def agent_chat(req: AgentChatReq):
    """Agent 对话入口，SSE 流式返回事件。"""
    ctx, cfg = _build_ctx()
    if not cfg.get("api_key"):
        raise HTTPException(400, "请先配置 LLM (api_key)")

    def event_stream():
        for ev in agent_loop.run_agent(ctx, req.message, cfg=cfg, history=req.history):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/rag/build-index")
def rag_build_index() -> dict:
    """构建/刷新 RAG 源码索引（扫描 ../projects 下所有 .py，AST chunking + embedding）。"""
    p = llm_config_path()
    cfg = _load_json(p) if p.exists() else {}
    if not cfg.get("api_key"):
        raise HTTPException(400, "请先配置 LLM (embedding 需要 api_key)")
    try:
        from rag.indexer import build_index
        stats = build_index(cfg, PROJECTS_DIR, rag_index_dir())
        return {"ok": True, "stats": stats}
    except Exception as e:
        raise HTTPException(500, f"构建索引失败: {e}")


@app.get("/api/rag/status")
def rag_status() -> dict:
    """返回 RAG 索引状态（已索引 chunk 数 / 构建时间 / 模型）。"""
    from rag import store as rag_store
    idx = rag_index_dir()
    meta = rag_store.read_meta(idx / "code_meta.json")
    chunks = rag_store.read_chunks(idx / "code_chunks.jsonl")
    return {"count": len(chunks), "built_at": meta.get("built_at", ""), "model": meta.get("model", "")}


class PublishReq(BaseModel):
    content: str          # 飞书 XML blocks
    title: str = "学习笔记"
    wiki_space_id: str | None = None


@app.post("/api/agent/publish-doc")
def agent_publish_doc(req: PublishReq) -> dict:
    """把 Agent 生成的文档发布到飞书(wiki 归档优先),返回 URL + kind。"""
    space = req.wiki_space_id
    if not space:
        lark_cfg_p = lark_config_path()
        if lark_cfg_p.exists():
            space = _load_json(lark_cfg_p).get("wiki_space_id")
    url, kind = publish_doc(req.content, req.title, wiki_space_id=space)
    if not url:
        raise HTTPException(500, "发布失败：请确认已执行 lark-cli auth login")
    return {"ok": True, "url": url, "kind": kind}


# ─────────────────────────── 飞书知识库归档配置 ───────────────────────────
class LarkConfigReq(BaseModel):
    wiki_space_id: str | None = None


def lark_config_path() -> Path:
    return DATA_ROOT / "lark_config.json"


@app.get("/api/lark/spaces")
def lark_spaces() -> dict:
    """列出当前用户的飞书知识库空间(调 lark-cli wiki +space-list)。"""
    import subprocess
    try:
        p = subprocess.run(["lark-cli", "wiki", "+space-list", "--as", "user", "--format", "json"],
                           capture_output=True, text=True, timeout=30)
        if p.returncode != 0:
            return {"ok": False, "spaces": [], "error": p.stderr[:200]}
        import json as _json
        data = _json.loads(p.stdout) if p.stdout.strip().startswith("{") else {"raw": p.stdout}
        # 防御性解析:lark-cli 输出格式可能变,尝试几种常见结构
        items = (data.get("data", {}).get("items")
                 or data.get("spaces")
                 or data.get("items")
                 or [])
        spaces = [{"space_id": s.get("space_id"), "name": s.get("name")} for s in items if isinstance(s, dict)]
        return {"ok": True, "spaces": spaces}
    except Exception as e:
        return {"ok": False, "spaces": [], "error": str(e)}


@app.put("/api/lark/config")
def put_lark_config(req: LarkConfigReq) -> dict:
    p = lark_config_path()
    cfg = _load_json(p) if p.exists() else {}
    if req.wiki_space_id is not None:
        cfg["wiki_space_id"] = req.wiki_space_id
    _save_json(p, cfg)
    return {"ok": True, "wiki_space_id": cfg.get("wiki_space_id")}


@app.get("/api/lark/config")
def get_lark_config() -> dict:
    p = lark_config_path()
    return _load_json(p) if p.exists() else {"wiki_space_id": None}


# ─────────────────────────── Chat 对话管理 ───────────────────────────
@app.get("/api/chat/history")
def get_chat_history() -> dict:
    return chat_store().load()


class ChatSyncReq(BaseModel):
    sessions: list
    current_session_id: str | None = None


@app.post("/api/chat/sync")
def chat_sync(req: ChatSyncReq) -> dict:
    chat_store().replace_all(req.sessions, req.current_session_id)
    return {"ok": True}


class ChatTitleReq(BaseModel):
    message: str


@app.post("/api/chat/title")
def chat_title(req: ChatTitleReq) -> dict:
    """LLM 生成会话标题。失败回退首句截断。"""
    p = llm_config_path()
    cfg = _load_json(p) if p.exists() else {}
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
def chat_search(q: str) -> dict:
    return {"hits": chat_store().search(q)}


@app.get("/api/chat/export")
def chat_export(session_id: str | None = None) -> dict:
    return chat_store().export(session_id)


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
def chat_resolve(refs: str) -> dict:
    trees = load_trees(DATA_ROOT)
    lay = layout_mod.compute_layout(trees)
    graph = {"nodes": lay["nodes"]}
    resources = _collect_resources(trees)
    # dirs 带上每个方向的节点 + state + pct（供 $ 引用展开）
    dirs = []
    for t in trees:
        dir_nodes = []
        for b in t.get("branches", []):
            for n in b.get("nodes", []):
                m, tot, pct = progress_mod.node_mastery(n)
                dir_nodes.append({"id": n.get("id"), "name": n.get("name"),
                                  "state": progress_mod.node_status(n), "pct": pct,
                                  "depends_on": n.get("depends_on", [])})
        dirs.append({"id": t.get("tree_id"), "title": t.get("title", ""),
                     "icon": t.get("icon", ""), "color": t.get("color", ""),
                     "nodes": dir_nodes})
    return {"resolved": chat_store().resolve_refs(refs, graph, dirs, resources)}


@app.get("/api/chat/suggest")
def chat_suggest(type: str, q: str) -> dict:
    trees = load_trees(DATA_ROOT)
    lay = layout_mod.compute_layout(trees)
    dirs = lay["dir_order"]
    graph = {"nodes": lay["nodes"]}
    resources = _collect_resources(trees)
    return {"items": chat_store().suggest(type, q, graph, dirs, resources)}


# ─────────────────────────── 其他板块 ───────────────────────────
@app.get("/api/profile")
def get_profile() -> dict:
    p = DATA_ROOT / "profile.json"
    if not p.exists():
        return {"name": "default", "contact": {}, "education": [], "skills": [], "experience": [], "awards": []}
    return _load_json(p)


TEMPLATE_META = {
    "billryan":    {"name": "Billryan", "style": "中英混合", "lang": "中英文", "scene": "国内大厂", "star": True},
    "sb2nov":      {"name": "sb2nov", "style": "极简单栏", "lang": "英文", "scene": "ATS 投递，外企"},
    "jakegut":     {"name": "Jake Gut", "style": "现代单栏", "lang": "英文", "scene": "科技公司，硅谷风"},
    "hijiangtao":  {"name": "hijiangtao", "style": "纯中文", "lang": "中文", "scene": "国内互联网"},
    "luooofan":    {"name": "luooofan", "style": "纯中文", "lang": "中文", "scene": "模块化结构，易维护"},
    "deedy":       {"name": "Deedy", "style": "双栏高密度", "lang": "英文", "scene": "经历多，一页塞满"},
    "awesome-cv":  {"name": "Awesome CV", "style": "彩色精致", "lang": "英文", "scene": "视觉美观"},
}


@app.get("/api/templates")
def get_templates() -> list[dict]:
    out = []
    if not TEMPLATES_DIR.exists():
        return out
    for d in sorted(os.listdir(TEMPLATES_DIR)):
        full = TEMPLATES_DIR / d
        if not full.is_dir():
            continue
        meta = dict(TEMPLATE_META.get(d, {"name": d, "style": "—", "lang": "—", "scene": "—"}))
        meta["id"] = d
        out.append(meta)
    return out


@app.get("/api/fruits")
def get_fruits() -> list[dict]:
    trees = load_trees(DATA_ROOT)
    tree_by_id = {t["tree_id"]: t for t in trees}
    out = []
    if not PROFILES_DIR.exists():
        return out
    for d in sorted(os.listdir(PROFILES_DIR)):
        pdir = PROFILES_DIR / d
        if not pdir.is_dir():
            continue
        tree = tree_by_id.get(d)
        pct = progress_mod.tree_progress(tree.get("branches", []))[2] if tree else 0
        pdf = BUILD_DIR / f"{d}.pdf"
        out.append({
            "id": d, "title": tree["title"] if tree else d, "icon": tree.get("icon", "📄") if tree else "📄",
            "subtitle": tree.get("subtitle", "") if tree else "", "color": tree.get("color", "#4ade80") if tree else "#4ade80",
            "pct": pct, "has_pdf": pdf.exists(),
        })
    return out


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "data_root": str(DATA_ROOT)}
