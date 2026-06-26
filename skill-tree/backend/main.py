"""main.py — FastAPI 后端。

数据源：../data/*.json (方向节点 + profile.json + achievements.json)
API:
  GET  /api/graph          合并去重 + 布局 + 掌握度 + 成就 + 总览
  PATCH /api/task          勾选/取消勾选任务(写回 JSON)
  GET  /api/profile        个人信息
  GET  /api/templates      简历模板
  GET  /api/fruits         果实(简历成品)
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

HERE = Path(__file__).resolve().parent
# 路径可通过环境变量覆盖（容器/本地不同）；默认按本地目录结构
DATA_DIR = Path(os.environ.get("DATA_DIR", HERE.parent / "data"))
RESUME_DIR = Path(os.environ.get("RESUME_DIR", HERE.parent.parent / "resume"))
TEMPLATES_DIR = RESUME_DIR / "templates"
PROFILES_DIR = RESUME_DIR / "profiles"
BUILD_DIR = RESUME_DIR / "build"
PROJECTS_DIR = Path(os.environ.get("PROJECTS_DIR", HERE.parent.parent / "projects"))

app = FastAPI(title="Skill Tree API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
# 托管 projects/ 的源码（节点 resource 指向 ../../projects/... → 前端走 /projects 代理）
if PROJECTS_DIR.exists():
    app.mount("/projects", StaticFiles(directory=str(PROJECTS_DIR)), name="projects")
# 托管编译好的简历 PDF（果实展示「打开 PDF」）
if BUILD_DIR.exists():
    app.mount("/resume", StaticFiles(directory=str(RESUME_DIR)), name="resume")


def _load_json(p: Path) -> Any:
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_json(p: Path, data: Any) -> None:
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_trees() -> list[dict]:
    trees = []
    for p in glob.glob(str(DATA_DIR / "*.json")):
        if os.path.basename(p) in ("achievements.json", "profile.json"):
            continue
        trees.append(_load_json(Path(p)))
    trees.sort(key=lambda t: (t.get("order", 99), t.get("tree_id", "")))
    return trees


def load_achievements() -> dict:
    p = DATA_DIR / "achievements.json"
    return _load_json(p) if p.exists() else {"achievements": []}


# ─────────────────────────── 图谱 ───────────────────────────
@app.get("/api/graph")
def get_graph() -> dict:
    trees = load_trees()
    achievements = load_achievements()
    lay = layout_mod.compute_layout(trees)
    # 给每个节点附掌握度
    node_map = {n["id"]: n for n in lay["nodes"]}
    # 从原始 trees 取节点对象算 mastery（含完整 tasks/verify）
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
    # 成就
    ach_results = progress_mod.evaluate_achievements(trees, achievements)
    # 总览
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
    }


# ─────────────────────────── 勾选 ───────────────────────────
class TaskPatch(BaseModel):
    tree_id: str
    node_id: str
    task_id: str
    done: bool
    is_verify: bool = False   # 是否验收任务


def _find_task_obj(trees: list[dict], tree_id: str, node_id: str, task_id: str, is_verify: bool):
    """定位到 data JSON 里对应的任务对象，返回 (tree_path, node, task)。"""
    for p in glob.glob(str(DATA_DIR / "*.json")):
        t = _load_json(Path(p))
        if t.get("tree_id") != tree_id:
            continue
        for b in t.get("branches", []):
            for n in b.get("nodes", []):
                if n["id"] != node_id:
                    continue
                # 在该节点的 tasks（及其 verify）里找
                for tk in n.get("tasks", []):
                    if not is_verify and tk["id"] == task_id:
                        return Path(p), n, tk
                    for v in tk.get("verify", []):
                        if v["id"] == task_id:
                            return Path(p), n, v
                # 兼容节点级 verify
                for v in n.get("verify", []):
                    if v["id"] == task_id:
                        return Path(p), n, v
    return None, None, None


@app.patch("/api/task")
def patch_task(patch: TaskPatch) -> dict:
    trees = load_trees()
    path, node, task = _find_task_obj(trees, patch.tree_id, patch.node_id, patch.task_id, patch.is_verify)
    if task is None:
        raise HTTPException(404, f"task not found: {patch.tree_id}/{patch.node_id}/{patch.task_id}")
    # _find_task_obj 改的是从磁盘读进来的 dict 引用；重新加载完整 tree 并原地改写回磁盘，
    # 保证文件格式(indent/顺序)稳定，不破坏其它字段。
    full = _load_json(path)
    # 在 full 里重新定位同一 task 改 done（避免引用了已被丢弃的对象）
    _apply_done(full, patch.node_id, patch.task_id, patch.done)
    _save_json(path, full)
    return get_graph()


def _apply_done(tree: dict, node_id: str, task_id: str, done: bool) -> None:
    for b in tree.get("branches", []):
        for n in b.get("nodes", []):
            if n["id"] != node_id:
                continue
            for tk in n.get("tasks", []):
                if tk["id"] == task_id:
                    tk["done"] = done
                    return
                for v in tk.get("verify", []):
                    if v["id"] == task_id:
                        v["done"] = done
                        return
            for v in n.get("verify", []):
                if v["id"] == task_id:
                    v["done"] = done
                    return


# ─────────────────────────── 其他板块 ───────────────────────────
@app.get("/api/profile")
def get_profile() -> dict:
    p = DATA_DIR / "profile.json"
    if not p.exists():
        raise HTTPException(404, "profile.json not found")
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
    trees = load_trees()
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
            "id": d,
            "title": tree["title"] if tree else d,
            "icon": tree.get("icon", "📄") if tree else "📄",
            "subtitle": tree.get("subtitle", "") if tree else "",
            "color": tree.get("color", "#4ade80") if tree else "#4ade80",
            "pct": pct,
            "has_pdf": pdf.exists(),
        })
    return out


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "data_dir": str(DATA_DIR)}
