"""main.py — FastAPI 后端（多用户 + AI 生成）。

用户隔离：data/users/<user_id>/，每个用户独立存树/profile/成就/llm配置。
user_id 来自请求头 X-User-Id（缺省 default）。将来换成 Depends(get_current_user) 做真鉴权。

API:
  GET  /api/graph          合并去重 + 布局 + 掌握度 + 成就 + 总览
  PATCH /api/task          勾选/取消勾选任务(写回 JSON)
  GET  /api/profile        个人信息
  GET  /api/templates      简历模板
  GET  /api/fruits         果实(简历成品)
  GET  /api/users          列出用户
  POST /api/users          新建用户
  GET/PUT /api/llm-config  读/存该用户 LLM 配置
  POST /api/llm-config/test  测连通
  POST /api/ai/generate-tree|direction|node   AI 生成
"""
from __future__ import annotations
import glob
import json
import os
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Header, Request
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
DATA_ROOT = Path(os.environ.get("DATA_ROOT", HERE.parent / "data"))
USERS_DIR = DATA_ROOT / "users"
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


def rag_index_dir(uid: str) -> Path:
    """每用户独立 RAG 索引目录。"""
    d = user_dir(uid) / "rag_index"
    d.mkdir(parents=True, exist_ok=True)
    return d


def chat_store_path(uid: str) -> Path:
    return user_dir(uid) / "chat_history.json"


def chat_store(uid: str) -> ChatStore:
    return ChatStore(chat_store_path(uid))


# ─────────────────────────── 用户与存储抽象 ───────────────────────────
_SAFE_ID = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fa5\-]{1,32}$")   # 用户名：字母数字下划线-中文，1-32


def resolve_user(x_user_id: str | None) -> str:
    """从请求头解析 user_id（现在：透传；将来：换鉴权实现）。校验合法性。"""
    uid = (x_user_id or "default").strip()
    if not _SAFE_ID.match(uid):
        raise HTTPException(400, f"invalid user_id: {uid!r}")
    return uid


def user_dir(uid: str) -> Path:
    d = USERS_DIR / uid
    d.mkdir(parents=True, exist_ok=True)
    return d


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
def get_graph(x_user_id: str | None = Header(default=None)) -> dict:
    uid = resolve_user(x_user_id)
    dd = user_dir(uid)
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
        "user_id": uid,
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
def patch_task(patch: TaskPatch, x_user_id: str | None = Header(default=None)) -> dict:
    uid = resolve_user(x_user_id)
    dd = user_dir(uid)
    path = _find_tree_file(dd, patch.tree_id)
    if path is None:
        raise HTTPException(404, f"tree not found: {patch.tree_id}")
    full = _load_json(path)
    if not _apply_done(full, patch.node_id, patch.task_id, patch.done):
        raise HTTPException(404, f"task not found: {patch.tree_id}/{patch.node_id}/{patch.task_id}")
    _save_json(path, full)
    SESSIONS.invalidate_snapshot(uid, "graph")
    return get_graph(x_user_id=uid)


# ─────────────────────────── 用户管理 ───────────────────────────
@app.get("/api/users")
def list_users() -> list[dict]:
    out = []
    if USERS_DIR.exists():
        for d in sorted(USERS_DIR.iterdir()):
            if d.is_dir():
                prof_p = d / "profile.json"
                name = _load_json(prof_p).get("name", d.name) if prof_p.exists() else d.name
                out.append({"id": d.name, "name": name})
    return out


class NewUser(BaseModel):
    user_id: str


@app.post("/api/users")
def create_user(req: NewUser) -> dict:
    if not _SAFE_ID.match(req.user_id):
        raise HTTPException(400, "user_id 只允许字母数字下划线-中文(1-32)")
    dd = user_dir(req.user_id)
    # 初始化空 profile + 默认成就(若不存在)
    prof_p = dd / "profile.json"
    if not prof_p.exists():
        _save_json(prof_p, {"name": req.user_id, "contact": {}, "education": [], "skills": [], "experience": [], "awards": []})
    ach_p = dd / "achievements.json"
    if not ach_p.exists():
        default_ach = USERS_DIR / "default" / "achievements.json"
        if default_ach.exists():
            _save_json(ach_p, _load_json(default_ach))
        else:
            _save_json(ach_p, {"achievements": []})
    return {"id": req.user_id, "created": True}


# ─────────────────────────── LLM 配置 ───────────────────────────
class LlmConfig(BaseModel):
    provider: str = ""
    base_url: str = ""
    api_key: str = ""
    model: str = ""


def llm_config_path(uid: str) -> Path:
    return user_dir(uid) / "llm_config.json"


@app.get("/api/llm-config")
def get_llm_config(x_user_id: str | None = Header(default=None)) -> dict:
    uid = resolve_user(x_user_id)
    p = llm_config_path(uid)
    if not p.exists():
        return {"provider": "", "base_url": "", "api_key": "", "model": "", "configured": False}
    cfg = _load_json(p)
    cfg["configured"] = bool(cfg.get("api_key") and cfg.get("base_url"))
    return cfg


@app.put("/api/llm-config")
def put_llm_config(cfg: LlmConfig, x_user_id: str | None = Header(default=None)) -> dict:
    uid = resolve_user(x_user_id)
    p = llm_config_path(uid)
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
def gen_tree(req: GenTreeReq, x_user_id: str | None = Header(default=None)) -> dict:
    uid = resolve_user(x_user_id)
    cfg = _load_json(llm_config_path(uid)) if llm_config_path(uid).exists() else {}
    if not cfg.get("api_key"):
        raise HTTPException(400, "请先配置 LLM (api_key)")
    try:
        result = ai_mod.generate_tree(cfg, req.jd, req.extra)
        return {"ok": True, "data": result}
    except Exception as e:
        raise HTTPException(500, f"生成失败: {e}")


@app.post("/api/ai/generate-direction")
def gen_direction(req: GenDirectionReq, x_user_id: str | None = Header(default=None)) -> dict:
    uid = resolve_user(x_user_id)
    cfg = _load_json(llm_config_path(uid)) if llm_config_path(uid).exists() else {}
    if not cfg.get("api_key"):
        raise HTTPException(400, "请先配置 LLM")
    try:
        result = ai_mod.generate_direction(cfg, req.description, req.existing_ids)
        return {"ok": True, "data": result}
    except Exception as e:
        raise HTTPException(500, f"生成失败: {e}")


@app.post("/api/ai/generate-node")
def gen_node(req: GenNodeReq, x_user_id: str | None = Header(default=None)) -> dict:
    uid = resolve_user(x_user_id)
    cfg = _load_json(llm_config_path(uid)) if llm_config_path(uid).exists() else {}
    if not cfg.get("api_key"):
        raise HTTPException(400, "请先配置 LLM")
    try:
        result = ai_mod.generate_node(cfg, req.description, req.node_id, req.existing_ids)
        return {"ok": True, "data": result}
    except Exception as e:
        raise HTTPException(500, f"生成失败: {e}")


@app.post("/api/ai/apply-tree")
def apply_tree(payload: dict, x_user_id: str | None = Header(default=None)) -> dict:
    """把 AI 生成的树写回用户目录（覆盖现有方向）。payload: {trees:[...], profile:{}}"""
    uid = resolve_user(x_user_id)
    dd = user_dir(uid)
    trees = payload.get("trees", [])
    for t in trees:
        fname = f"{t.get('tree_id','gen')}.json"
        _save_json(dd / fname, t)
    if payload.get("profile"):
        _save_json(dd / "profile.json", payload["profile"])
    SESSIONS.invalidate_snapshot(uid, "graph")
    return {"ok": True, "written": len(trees)}


@app.post("/api/ai/apply-direction")
def apply_direction(payload: dict, x_user_id: str | None = Header(default=None)) -> dict:
    """把 AI 生成的单方向作为新文件写入。payload: {tree: {...}}"""
    uid = resolve_user(x_user_id)
    dd = user_dir(uid)
    t = payload.get("tree", {})
    if t:
        fname = f"{t.get('tree_id','gen_dir')}.json"
        _save_json(dd / fname, t)
    SESSIONS.invalidate_snapshot(uid, "graph")
    return {"ok": True}


# ─────────────────────────── Agent 对话(SSE) ───────────────────────────
class AgentChatReq(BaseModel):
    message: str


def _build_ctx(uid: str) -> tuple[agent_tool.Context, dict]:
    """组装工具执行上下文：当前图谱(layout+掌握度) + 简历 + retriever + 勾选回调。"""
    dd = user_dir(uid)
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
    cfg = _load_json(llm_config_path(uid)) if llm_config_path(uid).exists() else {}
    retriever = Retriever(index_dir=rag_index_dir(uid), cfg=cfg)

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
                             retriever=retriever, rag_index_dir=rag_index_dir(uid), trees=trees)
    ctx.on_toggle = on_toggle  # type: ignore[attr-defined]
    return ctx, cfg


@app.post("/api/agent/chat")
def agent_chat(req: AgentChatReq, x_user_id: str | None = Header(default=None)):
    """Agent 对话入口，SSE 流式返回事件。"""
    uid = resolve_user(x_user_id)
    ctx, cfg = _build_ctx(uid)
    if not cfg.get("api_key"):
        raise HTTPException(400, "请先配置 LLM (api_key)")

    def event_stream():
        for ev in agent_loop.run_agent(ctx, req.message, cfg=cfg):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/rag/build-index")
def rag_build_index(x_user_id: str | None = Header(default=None)) -> dict:
    """构建/刷新 RAG 源码索引（扫描 ../projects 下所有 .py，AST chunking + embedding）。"""
    uid = resolve_user(x_user_id)
    cfg = _load_json(llm_config_path(uid)) if llm_config_path(uid).exists() else {}
    if not cfg.get("api_key"):
        raise HTTPException(400, "请先配置 LLM (embedding 需要 api_key)")
    try:
        from rag.indexer import build_index
        stats = build_index(cfg, PROJECTS_DIR, rag_index_dir(uid))
        return {"ok": True, "stats": stats}
    except Exception as e:
        raise HTTPException(500, f"构建索引失败: {e}")


@app.get("/api/rag/status")
def rag_status(x_user_id: str | None = Header(default=None)) -> dict:
    """返回 RAG 索引状态（已索引 chunk 数 / 构建时间 / 模型）。"""
    uid = resolve_user(x_user_id)
    from rag import store as rag_store
    meta = rag_store.read_meta(rag_index_dir(uid) / "code_meta.json")
    chunks = rag_store.read_chunks(rag_index_dir(uid) / "code_chunks.jsonl")
    return {"count": len(chunks), "built_at": meta.get("built_at", ""), "model": meta.get("model", "")}


class PublishReq(BaseModel):
    content: str          # 飞书 XML blocks
    title: str = "学习笔记"


@app.post("/api/agent/publish-doc")
def agent_publish_doc(req: PublishReq, x_user_id: str | None = Header(default=None)) -> dict:
    """把 Agent 生成的文档内容发布到飞书，返回飞书文档 URL。"""
    url = publish_doc(req.content, req.title)
    if not url:
        raise HTTPException(500, "发布失败：请确认已执行 lark-cli auth login")
    return {"ok": True, "url": url}


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
def chat_export(session_id: str | None = None, x_user_id: str | None = Header(default=None)) -> dict:
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
    return {"resolved": chat_store(uid).resolve_refs(refs, graph, dirs, resources)}


@app.get("/api/chat/suggest")
def chat_suggest(type: str, q: str, x_user_id: str | None = Header(default=None)) -> dict:
    uid = resolve_user(x_user_id)
    trees = load_trees(user_dir(uid))
    lay = layout_mod.compute_layout(trees)
    dirs = lay["dir_order"]
    graph = {"nodes": lay["nodes"]}
    resources = _collect_resources(trees)
    return {"items": chat_store(uid).suggest(type, q, graph, dirs, resources)}


# ─────────────────────────── 其他板块 ───────────────────────────
@app.get("/api/profile")
def get_profile(x_user_id: str | None = Header(default=None)) -> dict:
    uid = resolve_user(x_user_id)
    p = user_dir(uid) / "profile.json"
    if not p.exists():
        return {"name": uid, "contact": {}, "education": [], "skills": [], "experience": [], "awards": []}
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
def get_fruits(x_user_id: str | None = Header(default=None)) -> list[dict]:
    uid = resolve_user(x_user_id)
    trees = load_trees(user_dir(uid))
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
