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
        if os.path.basename(p) in ("achievements.json", "profile.json", "llm_config.json"):
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
        if os.path.basename(p) in ("achievements.json", "profile.json", "llm_config.json"):
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
    return {"ok": True}


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
