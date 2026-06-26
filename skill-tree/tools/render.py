#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
render.py — 技能树生成器（零依赖，纯标准库）

唯一数据源：  skill-tree/data/*.json (任意领域技能树) + achievements.json (成就)
             data/ 下每个 *.json(除 achievements.json) 自动识别为一棵树
             → 天然泛化：新增实习领域只需丢一个 JSON 进 data/
生成产物：    skill-tree/dist/skill-tree.html  (交互式, 浏览器打开)
             skill-tree/dist/PROGRESS.md      (Markdown 进度表, GitHub/Obsidian 可读)

用法：  python skill-tree/tools/render.py

进度保存机制：HTML 里勾选子任务用 localStorage 本地保存，刷新不丢。
            本脚本读 JSON 里的 done 字段作为"默认进度"，浏览器里的勾选覆盖之。
"""
import glob
import json
import os
import re
import sys
from html import escape

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_TREE_DIR = os.path.dirname(HERE)          # skill-tree/
DATA_DIR = os.path.join(SKILL_TREE_DIR, "data")
DIST_DIR = os.path.join(SKILL_TREE_DIR, "dist")


# ─────────────────────────── 数据加载（目录驱动·泛化）───────────────────────────
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_all():
    """data/ 下除 achievements.json / profile.json 外，每个 *.json 自动算一个方向。"""
    trees = []
    for p in glob.glob(os.path.join(DATA_DIR, "*.json")):
        base = os.path.basename(p)
        if base in ("achievements.json", "profile.json"):
            continue
        trees.append(load_json(p))
    # order 字段优先；缺省按文件名。保证展示顺序稳定可控。
    trees.sort(key=lambda t: (t.get("order", 99), t.get("tree_id", "")))
    ach_path = os.path.join(DATA_DIR, "achievements.json")
    achievements = load_json(ach_path) if os.path.exists(ach_path) else {"achievements": []}
    return trees, achievements


# ─────────────────────────── 进度计算 ───────────────────────────
def _all_tasks(node):
    """学习任务 + 它们各自的 verify 子任务（仅用于渲染勾选框，不用于掌握度统计）。"""
    out = []
    for t in node.get("tasks", []):
        out.append(t)
        out.extend(t.get("verify", []))
    out.extend(node.get("verify", []))   # 兼容旧数据
    return out


def node_mastery(node):
    """以「知识点」为单位算掌握度：一个学习任务 = 一个知识点。
    - 有 verify 的知识点：所有验收 done 才算掌握（学习任务勾选不计）
    - 无 verify 的知识点：学习任务 done 即掌握
    返回 (mastered数, 知识点总数, pct)。
    """
    points = node.get("tasks", [])
    total = len(points)
    mastered = 0
    for tk in points:
        ver = tk.get("verify", [])
        if ver:
            if all(v.get("done") for v in ver):
                mastered += 1
        else:
            if tk.get("done"):
                mastered += 1
    pct = 100 if total == 0 else round(mastered / total * 100)
    return mastered, total, pct


def node_progress(node):
    """节点进度 = 掌握的知识点数（与点灯逻辑一致）。"""
    m, t, pct = node_mastery(node)
    return m, t, pct


def node_status(node):
    mastered, total, _ = node_progress(node)
    # 所有知识点都掌握 → done
    if total > 0 and mastered == total:
        return "done"
    if total == 0 and node.get("status") == "done":
        return "done"   # 无任务节点：尊重显式 status
    # 有任何勾选进展(学习清单或验收) → learning
    if any(tk.get("done") for tk in _all_tasks(node)) or node.get("status") in ("learning", "done"):
        return "learning"
    return "locked"


def branch_progress(branch):
    nodes = branch.get("nodes", [])
    tot_d, tot_t = 0, 0
    for n in nodes:
        d, t, _ = node_progress(n)
        tot_d += d; tot_t += t
    pct = 0 if tot_t == 0 else round(tot_d / tot_t * 100)
    return tot_d, tot_t, pct


def tree_progress(tree):
    tot_d, tot_t = 0, 0
    for b in tree.get("branches", []):
        d, t, _ = branch_progress(b)
        tot_d += d; tot_t += t
    pct = 0 if tot_t == 0 else round(tot_d / tot_t * 100)
    return tot_d, tot_t, pct


# ─────────────────────────── 单画布 DAG 布局（整个仓库 = 一棵树）───────────────────────────
# 布局常量（px）
NODE_W = 168
NODE_H = 96          # 节点卡片高度（详情折叠前）
COL_GAP = 26         # 同层节点水平间距
ROW_GAP = 176        # 层间垂直间距（>NODE_H，给连线留充足可见空间）
CANVAS_PAD = 48      # 画布内边距


def _branch_leaf(branch):
    """返回某分支的"末端节点" id：不被本分支其他节点依赖的节点。用于解析 branch-id 依赖。"""
    nodes = branch.get("nodes", [])
    ids = {n["id"] for n in nodes}
    depended = set()
    for n in nodes:
        for d in n.get("depends_on", []):
            if d in ids:
                depended.add(d)
    leaves = [n["id"] for n in nodes if n["id"] not in depended]
    return leaves[-1] if leaves else (nodes[-1]["id"] if nodes else None)


def merge_nodes(trees):
    """合并所有树的节点，按 id 去重。返回 (nodes_by_id, dirs_by_id, dir_order)。

    - nodes_by_id: {id: node}  (同名取首个，合并 tasks 以更完整者为准)
    - dirs_by_id:  {id: [(dir_id, dir_color, branch_id), ...]}  节点归属的方向
    - dir_order:   [(dir_id, tree_obj), ...] 按展示顺序
    """
    nodes_by_id = {}
    dirs_by_id = {}
    dir_order = []
    branch_index = {}  # branch_id -> (tree_id, branch_obj) 用于解析 branch 依赖
    for t in trees:
        dir_order.append(t)
        for b in t.get("branches", []):
            branch_index[b["id"]] = (t, b)
            for n in b.get("nodes", []):
                nid = n["id"]
                dirs_by_id.setdefault(nid, [])
                entry = (t["tree_id"], t.get("color", "#4ade80"), b["id"])
                # 去重方向条目
                if not any(e[0] == entry[0] for e in dirs_by_id[nid]):
                    dirs_by_id[nid].append(entry)
                if nid not in nodes_by_id:
                    nodes_by_id[nid] = n
                else:
                    # 合并：tasks 更完整者胜出
                    if len(n.get("tasks", [])) > len(nodes_by_id[nid].get("tasks", [])):
                        nodes_by_id[nid] = n
    return nodes_by_id, dirs_by_id, dir_order, branch_index


def normalize_deps(nodes_by_id, branch_index):
    """归一化依赖：branch-id → 该分支末端 node；过滤不存在的依赖。返回 {id: [dep_id,...]}。"""
    # branch_id → leaf node id
    branch_leaf = {bid: _branch_leaf(b) for bid, (_, b) in branch_index.items()}
    all_ids = set(nodes_by_id)
    norm = {}
    for nid, node in nodes_by_id.items():
        resolved = []
        for d in node.get("depends_on", []):
            if d in all_ids:
                resolved.append(d)
            elif d in branch_leaf and branch_leaf[d] and branch_leaf[d] in all_ids:
                resolved.append(branch_leaf[d])
        # 去重
        seen = set(); rd = []
        for d in resolved:
            if d not in seen:
                seen.add(d); rd.append(d)
        norm[nid] = rd
    return norm


def compute_depths(deps):
    """每个节点深度 = 从根(无依赖)出发的最长路径长度。迭代松弛，根=0。"""
    depth = {}
    # 反向：dependents
    def dpt(nid, stack):
        if nid in depth:
            return depth[nid]
        if nid in stack:  # 环保护
            return 0
        ds = deps.get(nid, [])
        if not ds:
            depth[nid] = 0
            return 0
        stack.add(nid)
        depth[nid] = 1 + max(dpt(d, stack) for d in ds if d in deps)
        stack.discard(nid)
        return depth[nid]
    for nid in deps:
        dpt(nid, set())
    return depth


def compute_dag_layout(trees):
    """整仓库合并成一张 DAG，算定每个节点的 (x, y, depth)。根在底部。

    返回 dict: { node_id: {node, x, y, depth, dirs, edges:[(from_id,..)]} }
    以及画布尺寸 (w, h) 和按 depth 分组的行列表。
    """
    nodes_by_id, dirs_by_id, dir_order, branch_index = merge_nodes(trees)
    deps = normalize_deps(nodes_by_id, branch_index)
    depth = compute_depths(deps)

    # 每个节点的"主方向序号"用于排序聚拢：取其首个归属方向的 order
    dir_rank = {t["tree_id"]: i for i, t in enumerate(dir_order)}
    # branch 在其树内的顺序
    branch_rank = {}
    for t in dir_order:
        for i, b in enumerate(t.get("branches", [])):
            branch_rank[(t["tree_id"], b["id"])] = i
    node_seq = {}  # 全局出现序（稳定二级排序）
    seq = 0
    for t in dir_order:
        for b in t.get("branches", []):
            for n in b.get("nodes", []):
                if n["id"] not in node_seq:
                    node_seq[n["id"]] = seq; seq += 1

    def sort_key(nid):
        dirs = dirs_by_id.get(nid, [])
        primary = dir_rank.get(dirs[0][0], 99) if dirs else 99
        brank = branch_rank.get((dirs[0][0], dirs[0][2]), 99) if dirs else 99
        return (primary, brank, node_seq.get(nid, 999))

    max_depth = max(depth.values()) if depth else 0
    # 按 depth 分行并排序
    rows = {d: [] for d in range(max_depth + 1)}
    for nid in nodes_by_id:
        rows[depth[nid]].append(nid)
    for d in rows:
        rows[d].sort(key=sort_key)

    # 算坐标：y 从顶部往下（depth 0 = 基础/根 在最上，向下生长）
    # 画布高度 = (max_depth+1) * ROW_GAP
    canvas_h = (max_depth + 1) * ROW_GAP + CANVAS_PAD * 2
    max_row_w = 0
    pos = {}
    for d, ids in rows.items():
        n = len(ids)
        row_w = n * NODE_W + (n - 1) * COL_GAP if n > 0 else 0
        max_row_w = max(max_row_w, row_w)
        # y: depth 0 在顶部，向下递增
        y = CANVAS_PAD + d * ROW_GAP
        for i, nid in enumerate(ids):
            x = CANVAS_PAD + i * (NODE_W + COL_GAP)
            pos[nid] = {"x": x, "y": y, "depth": d}
    canvas_w = max_row_w + CANVAS_PAD * 2

    # 边列表
    edges = []
    for nid, ds in deps.items():
        for d in ds:
            edges.append((d, nid))  # from=dep(更深在底), to=node(更浅在顶) → 视觉上 from 在下

    layout = {}
    for nid, node in nodes_by_id.items():
        layout[nid] = {
            "node": node,
            "x": pos[nid]["x"], "y": pos[nid]["y"],
            "depth": pos[nid]["depth"],
            "dirs": dirs_by_id.get(nid, []),
        }
    return {
        "layout": layout,
        "edges": edges,
        "canvas_w": canvas_w,
        "canvas_h": canvas_h,
        "max_depth": max_depth,
        "dir_order": dir_order,
    }


# ─────────────────────────── 成就判定 ───────────────────────────
def evaluate_achievements(trees, achievements):
    node_idx = {}
    for t in trees:
        for b in t.get("branches", []):
            for n in b.get("nodes", []):
                node_idx[n["id"]] = n

    all_tasks = []
    for t in trees:
        for b in t.get("branches", []):
            for n in b.get("nodes", []):
                all_tasks.extend(n.get("tasks", []))

    total_tasks_done = sum(1 for tk in all_tasks if tk.get("done"))
    total_nodes_done = sum(1 for n in node_idx.values() if node_status(n) == "done")
    tree_pcts = {t["tree_id"]: tree_progress(t)[2] for t in trees}

    results = []
    for ach in achievements["achievements"]:
        cond = ach["condition"]
        ct = cond["type"]
        ok = False
        if ct == "nodes_done":
            ok = total_nodes_done >= cond["min"]
        elif ct == "tasks_done":
            ok = total_tasks_done >= cond["min"]
        elif ct == "tree_progress":
            ok = any(p >= cond["min"] for p in tree_pcts.values())
        elif ct == "all_trees_progress":
            ok = bool(tree_pcts) and all(p >= cond["min"] for p in tree_pcts.values())
        elif ct == "branch_done":
            tid = cond.get("tree_id"); bid = cond["branch_id"]
            for t in trees:
                if tid and t["tree_id"] != tid:
                    continue
                for b in t.get("branches", []):
                    if b["id"] == bid and b.get("nodes") and all(node_status(n) == "done" for n in b["nodes"]):
                        ok = True
        elif ct == "task_resource_contains":
            sub = cond["substring"]
            ok = sum(1 for tk in all_tasks if tk.get("done") and sub in tk.get("resource", "")) >= cond["min"]
        elif ct == "task_keyword":
            kw = cond["keyword"]
            ok = sum(1 for tk in all_tasks if tk.get("done") and kw in tk.get("title", "")) >= cond["min"]
        results.append((ach, ok))
    return results


# ─────────────────────────── 设计系统（活力有机森林）───────────────────────────
CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700;9..144,900&family=Manrope:wght@400;500;600;700&family=Noto+Serif+SC:wght@500;700;900&display=swap');

:root{
  --ink:#0a1612;            /* 深夜森林底色 */
  --ink-2:#0e2019;
  --moss:#13291f;           /* 苔藓面板 */
  --moss-2:#1a3a2c;
  --line:#26453a;
  --bark:#3d5e4f;
  --fg:#eaf5ee;
  --fg-dim:#9fb9ab;
  --fg-faint:#5e7a6c;
  --growth:#4ade80;         /* 生长绿·done */
  --growth-glow:rgba(74,222,128,.55);
  --bud:#fbbf24;            /* 花苞金·learning */
  --bud-glow:rgba(251,191,36,.5);
  --seed:#2f4a3d;           /* 种子·locked */
  --gold:#fde68a;
  --pearl:#f3f7f4;
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{
  font-family:'Manrope','Noto Serif SC',-apple-system,"Microsoft YaHei",sans-serif;
  background:var(--ink);
  color:var(--fg);
  line-height:1.65;
  min-height:100vh;
  overflow-x:hidden;
  /* 森林氛围：层叠光晕 + 极轻噪点 */
  background-image:
    radial-gradient(900px 600px at 12% -8%, rgba(74,222,128,.10), transparent 60%),
    radial-gradient(800px 700px at 92% 6%, rgba(251,191,36,.07), transparent 60%),
    radial-gradient(700px 700px at 50% 110%, rgba(34,197,94,.08), transparent 60%),
    url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.035 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>");
}
.serif{font-family:'Fraunces','Noto Serif SC',serif}

/* ───────── 应用骨架：侧栏 + 主区 ───────── */
.app{display:grid;grid-template-columns:248px 1fr;min-height:100vh}
.sidebar{position:sticky;top:0;height:100vh;background:linear-gradient(180deg,var(--ink-2),var(--ink));border-right:1px solid var(--line);display:flex;flex-direction:column;padding:26px 18px 20px;z-index:20}
.sb-brand{padding:6px 10px 22px;border-bottom:1px solid var(--line);margin-bottom:18px}
.sb-logo{font-size:30px;line-height:1;margin-bottom:10px;filter:drop-shadow(0 0 10px var(--growth-glow))}
.sb-name{font-size:22px;font-weight:700;line-height:1.15}
.sb-tag{font-size:11.5px;color:var(--fg-faint);margin-top:6px;line-height:1.4}
.sb-nav{display:flex;flex-direction:column;gap:4px;flex:1}
.sb-item{display:flex;align-items:center;gap:12px;padding:11px 14px;border-radius:12px;color:var(--fg-dim);text-decoration:none;font-size:14.5px;font-weight:500;transition:.22s;border:1px solid transparent}
.sb-item .sb-ico{font-size:18px;width:22px;text-align:center}
.sb-item:hover{background:var(--moss);color:var(--fg)}
.sb-item.active{background:var(--moss-2);color:var(--fg);border-color:var(--growth);box-shadow:0 0 18px -8px var(--growth-glow)}
.sb-item.active .sb-ico{filter:drop-shadow(0 0 6px var(--growth-glow))}
.sb-foot{border-top:1px solid var(--line);padding-top:18px;display:flex;align-items:center;gap:14px}
.sb-prog-ring{position:relative;width:56px;height:56px;flex-shrink:0}
.sb-prog-ring svg{transform:rotate(-90deg);width:56px;height:56px}
.sb-prog-ring circle{fill:none;stroke-width:5}
.ring-bg{stroke:var(--line)}
.ring-fg{stroke:var(--growth);stroke-linecap:round;stroke-dasharray:163.4;transition:stroke-dashoffset .8s cubic-bezier(.2,.8,.2,1);filter:drop-shadow(0 0 4px var(--growth-glow))}
.ring-txt{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-family:'Fraunces',serif;font-weight:900;font-size:15px}
.sb-stats{font-size:11.5px;color:var(--fg-faint);line-height:1.5}
.sb-stats b{color:var(--growth);font-family:'Fraunces',serif;font-size:14px}

.main{padding:40px 44px 60px;min-width:0;overflow-x:hidden}
.app-foot{margin-top:50px;text-align:center;color:var(--fg-faint);font-size:12px;padding-top:24px;border-top:1px solid var(--line)}
.app-foot code{background:var(--moss);padding:2px 8px;border-radius:6px;color:var(--growth);font-size:11px}
@media(max-width:820px){.app{grid-template-columns:1fr}.sidebar{position:static;height:auto;flex-direction:row;flex-wrap:wrap;gap:12px}.sb-brand,.sb-foot{border:none;padding:0;margin:0}.sb-nav{flex-direction:row;flex-wrap:wrap}.main{padding:24px 18px}}

/* ───────── 板块通用 ───────── */
.panel{display:none;animation:panelIn .4s cubic-bezier(.2,.8,.2,1) both}
.panel.active{display:block}
@keyframes panelIn{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
.panel-head{margin-bottom:30px}
.panel-title{font-size:34px;font-weight:700;letter-spacing:-.01em;display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
.panel-sub{color:var(--fg-dim);font-size:15px;margin-top:8px}
.panel-sub b{color:var(--growth);font-weight:600}
.name-en{font-size:18px;color:var(--fg-faint);font-family:'Fraunces',serif;font-style:italic;font-weight:400}
.empty{padding:40px;text-align:center;color:var(--fg-faint)}

/* 个人信息 */
.contact-row{display:flex;gap:18px;flex-wrap:wrap;margin-top:18px}
.contact-row .ci{font-size:13.5px;color:var(--fg-dim);background:var(--moss);border:1px solid var(--line);padding:6px 14px;border-radius:20px}
.contact-row .ci a{color:var(--growth);text-decoration:none}
.pgrid{display:grid;grid-template-columns:1fr 1fr;gap:36px;margin-top:28px}
@media(max-width:920px){.pgrid{grid-template-columns:1fr}}
.psec{font-family:'Fraunces','Noto Serif SC',serif;font-size:17px;font-weight:700;color:var(--fg);margin:0 0 14px;padding-left:12px;border-left:3px solid var(--growth)}
.edu-item{display:flex;justify-content:space-between;gap:14px;padding:9px 0;border-bottom:1px solid var(--line)}
.edu-main{display:flex;flex-direction:column}
.edu-school{font-weight:600;color:var(--fg)}
.edu-degree{font-size:13px;color:var(--fg-faint);margin-top:2px}
.edu-period{font-size:12.5px;color:var(--fg-faint);white-space:nowrap;font-family:'Fraunces',serif}
.skill-row{display:flex;gap:12px;padding:7px 0;align-items:flex-start}
.skill-group{font-size:12.5px;color:var(--bud);font-weight:700;min-width:78px;flex-shrink:0;padding-top:3px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{font-size:12px;background:var(--moss);border:1px solid var(--line);color:var(--fg-dim);padding:3px 10px;border-radius:14px}
.chip.sm{font-size:11px;padding:2px 8px}
.exp-card{background:var(--moss);border:1px solid var(--line);border-radius:16px;padding:18px 20px;margin-bottom:14px;transition:.25s}
.exp-card:hover{border-color:var(--growth);box-shadow:0 12px 30px -16px var(--growth-glow)}
.exp-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}
.exp-title{font-weight:700;font-size:16px;color:var(--fg)}
.exp-role{font-size:12.5px;color:var(--fg-faint);margin-top:3px}
.exp-period{font-size:12px;color:var(--growth);font-family:'Fraunces',serif;white-space:nowrap}
.exp-desc{font-size:13.5px;color:var(--fg-dim);margin:12px 0;line-height:1.6}
.exp-hl{list-style:none;margin:8px 0 0}
.exp-hl li{font-size:13px;color:var(--fg-dim);padding:3px 0 3px 18px;position:relative;line-height:1.5}
.exp-hl li::before{content:"▸";color:var(--growth);position:absolute;left:0}
.exp-link{display:inline-block;margin-top:10px;font-size:12.5px;color:var(--growth);text-decoration:none;border:1px solid var(--growth);padding:4px 12px;border-radius:14px}
.exp-link:hover{background:rgba(74,222,128,.1)}
.award-item{display:flex;gap:14px;padding:8px 0;border-bottom:1px solid var(--line);align-items:baseline}
.award-year{font-family:'Fraunces',serif;font-weight:700;color:var(--bud);min-width:46px;font-size:14px}
.award-title{font-size:13px;color:var(--fg-dim)}
.award-note{font-size:11px;color:var(--fg-faint)}
.lead-list{list-style:none}
.lead-list li{font-size:13px;color:var(--fg-dim);padding:6px 0 6px 18px;position:relative}
.lead-list li::before{content:"◆";color:var(--growth);position:absolute;left:0;font-size:9px;top:11px}

/* 模板卡片 */
.tcard-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:16px}
.tcard{display:block;background:linear-gradient(165deg,var(--moss-2),var(--moss));border:1px solid var(--line);border-radius:18px;padding:20px;text-decoration:none;color:inherit;transition:.28s cubic-bezier(.2,.8,.2,1);position:relative;overflow:hidden}
.tcard:hover{transform:translateY(-4px);border-color:var(--growth);box-shadow:0 18px 40px -18px var(--growth-glow)}
.tcard-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
.tname{font-size:21px;font-weight:700;color:var(--fg)}
.tstar{font-size:10.5px;color:var(--growth);background:rgba(74,222,128,.12);border:1px solid var(--growth);padding:3px 9px;border-radius:12px;font-weight:700}
.tmeta{display:flex;gap:8px;font-size:13px;color:var(--fg-faint);margin-bottom:8px}
.tscene{font-size:13.5px;color:var(--fg-dim);margin-bottom:14px}
.tcard-cta{font-size:13px;color:var(--growth);font-weight:600}

/* 果实卡片 */
.fcard-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:18px}
.fcard{background:linear-gradient(165deg,var(--moss-2),var(--moss));border:1px solid var(--line);border-radius:20px;padding:22px;position:relative;overflow:hidden}
.fcard::before{content:"";position:absolute;top:0;left:0;right:0;height:4px;background:var(--c)}
.fcard-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px}
.fico{font-size:34px;filter:drop-shadow(0 0 8px color-mix(in srgb,var(--c) 50%,transparent))}
.fstatus{font-size:11px;font-weight:700;padding:3px 10px;border-radius:12px}
.fstatus.ok{background:rgba(74,222,128,.12);color:var(--growth);border:1px solid var(--growth)}
.fstatus.no{background:rgba(148,163,184,.1);color:var(--fg-faint);border:1px solid var(--line)}
.fname{font-size:22px;font-weight:700;color:var(--fg)}
.fsub{font-size:13px;color:var(--fg-faint);margin-top:4px;min-height:18px}
.fbar{height:6px;background:var(--ink);border-radius:4px;overflow:hidden;margin:16px 0 6px;border:1px solid var(--line)}
.fbar > i{display:block;height:100%;background:var(--c);border-radius:4px;transition:width .6s}
.fpct{font-size:12px;color:var(--fg-faint)}
.fbtns{display:flex;gap:10px;margin-top:18px}
.fbtn{flex:1;text-align:center;font-size:13px;font-weight:600;padding:10px;border-radius:12px;text-decoration:none;border:1px solid var(--line);color:var(--fg-dim);transition:.22s}
.fbtn:hover{border-color:var(--fg-dim);color:var(--fg)}
.fbtn.primary{background:var(--growth);color:#062013;border-color:var(--growth)}
.fbtn.primary:hover{box-shadow:0 8px 22px -8px var(--growth-glow);color:#062013}
.fbtn.disabled{opacity:.4;cursor:not-allowed}

/* ───────── 总览仪表盘 ───────── */
.dashboard{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:0 0 10px}
@media(max-width:760px){.dashboard{grid-template-columns:repeat(2,1fr)}}
.metric{background:linear-gradient(160deg,var(--moss),var(--ink-2));border:1px solid var(--line);border-radius:18px;padding:20px 22px;position:relative;overflow:hidden}
.metric::after{content:"";position:absolute;inset:0;background:radial-gradient(120px 60px at 80% 0%,rgba(74,222,128,.12),transparent);pointer-events:none}
.metric .v{font-family:'Fraunces',serif;font-size:40px;font-weight:900;line-height:1;color:var(--fg)}
.metric .v .of{color:var(--fg-faint);font-weight:600;font-size:22px}
.metric .l{font-size:12.5px;color:var(--fg-dim);margin-top:8px;letter-spacing:.02em}

/* ───────── 成就花田 ───────── */
section.block{margin-top:54px}
.dag-block{margin-top:22px}
.section-title{display:flex;align-items:baseline;gap:14px;margin-bottom:22px}
.section-title h2{font-family:'Fraunces','Noto Serif SC',serif;font-size:30px;font-weight:700;letter-spacing:-.01em}
.section-title .hint{color:var(--fg-faint);font-size:13px}
.bloom-grid{display:flex;flex-wrap:wrap;gap:12px}
.bloom{display:flex;align-items:center;gap:10px;background:var(--moss);border:1px solid var(--line);border-radius:14px;padding:11px 16px 11px 12px;font-size:13.5px;position:relative;transition:.35s cubic-bezier(.2,.8,.2,1);opacity:.42;filter:saturate(.4) brightness(.8)}
.bloom .petal{font-size:24px;line-height:1;filter:grayscale(.5)}
.bloom .meta{display:flex;flex-direction:column}
.bloom .meta .n{font-weight:600;color:var(--fg)}
.bloom .meta .d{font-size:11.5px;color:var(--fg-faint)}
.bloom .tier{font-size:10px;font-weight:800;padding:2px 9px;border-radius:20px;letter-spacing:.04em;text-transform:uppercase}
.tier-gold{background:linear-gradient(135deg,#fde68a,#f59e0b);color:#3b2606}
.tier-silver{background:linear-gradient(135deg,#e2e8f0,#94a3b8);color:#1e293b}
.tier-bronze{background:linear-gradient(135deg,#fbbf24,#b45309);color:#2a1605}
.bloom.unlocked{opacity:1;filter:none;border-color:var(--growth);box-shadow:0 0 0 1px var(--growth-glow),0 10px 30px -12px var(--growth-glow)}
.bloom.unlocked .petal{filter:none;animation:bloomIn .6s cubic-bezier(.2,1.6,.4,1) both}
@keyframes bloomIn{0%{transform:scale(.3) rotate(-25deg);opacity:0}100%{transform:scale(1) rotate(0);opacity:1}}

/* ───────── 森林容器（整仓库一张图）───────── */
.forest-card{margin-top:30px;background:linear-gradient(180deg,var(--moss) 0%,var(--ink-2) 100%);border:1px solid var(--line);border-radius:28px;overflow:hidden;position:relative}
.forest-card::before{content:"";position:absolute;top:0;left:0;right:0;height:4px;background:linear-gradient(90deg,var(--growth),var(--bud));opacity:.8;z-index:3}
.forest-head{padding:26px 34px 22px;border-bottom:1px solid var(--line);display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.dir-legend{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.dir-chip{display:inline-flex;align-items:center;gap:7px;font-size:13.5px;font-weight:600;color:var(--fg-dim);background:var(--moss-2);border:1px solid var(--line);padding:6px 13px;border-radius:20px}
.dir-chip i{width:9px;height:9px;border-radius:50%;background:var(--c);box-shadow:0 0 8px var(--c)}
.dir-hint{font-size:12px;color:var(--fg-faint)}
.forest-title{font-family:'Fraunces','Noto Serif SC',serif;font-size:24px;font-weight:700;margin-right:auto}

/* ───────── 单画布 DAG（整仓库一棵树）───────── */
.dag-wrap{position:relative;overflow:auto;border-radius:0 0 24px 24px;border-top:1px solid var(--line)}
.dag-canvas{position:relative;margin:0 auto}
/* 根系氛围：底部一抹土壤光晕，呼应"根在底" */
.dag-canvas::after{content:"";position:absolute;left:0;right:0;top:0;height:120px;pointer-events:none;
  background:linear-gradient(180deg,rgba(74,222,128,.08),transparent)}

/* 连线 SVG 覆盖层 */
.edges{position:absolute;left:0;top:0;overflow:visible;pointer-events:none;z-index:1}
.edges path{fill:none;stroke:#5b8775;stroke-width:2;opacity:.7;transition:stroke .3s,opacity .3s}
.edges path.active{stroke:var(--growth);stroke-width:2.4;opacity:1;filter:drop-shadow(0 0 6px var(--growth-glow))}
.edges path.dim{opacity:.4}

/* 悬停高亮路径：画布 dim 态下，非路径节点/边淡化。
   关键：已展开(.open)的节点不淡化——详情面板要可读；悬停弹出位移在 dim 态关闭，避免与高亮冲突 */
.dag-canvas.dim .node:not(.onpath):not(.open){opacity:.16!important;filter:grayscale(.6)}
.dag-canvas.dim .node.onpath,.dag-canvas.dim .node.open{box-shadow:0 0 0 2px var(--growth),0 0 28px -6px var(--growth-glow);z-index:6}
.dag-canvas.dim .node{transform:none!important}                 /* dim 态关闭 hover 弹出位移 */
.dag-canvas.dim .node.onpath:hover{transform:none!important}
.dag-canvas.dim .edges path:not(.onpath){opacity:.06!important}
.dag-canvas.dim .edges path.onpath{stroke:var(--growth);stroke-width:2.6;opacity:1;filter:drop-shadow(0 0 7px var(--growth-glow))}

/* 深度刻度（左侧根系→树梢提示） */
.depth-axis{position:absolute;left:8px;top:0;bottom:0;width:14px;display:flex;flex-direction:column;justify-content:flex-start;pointer-events:none}
.depth-axis span{flex:1;display:flex;align-items:center;font-size:9px;color:var(--fg-faint);writing-mode:vertical-rl;letter-spacing:.1em;opacity:.5}

/* ───────── 节点·果实（绝对定位）───────── */
.node{position:absolute;width:168px;background:linear-gradient(165deg,var(--moss-2),var(--moss));border:1.5px solid var(--line);border-radius:18px;padding:14px 14px 12px;cursor:pointer;transition:transform .3s cubic-bezier(.2,.8,.2,1),background .3s,box-shadow .3s,border-color .3s;text-align:left;font-family:inherit;color:inherit;z-index:2}
.node:hover{transform:translateY(-3px);border-color:var(--fg-dim);box-shadow:0 18px 40px -18px rgba(0,0,0,.6);z-index:5}
.node.open{z-index:8}                       /* 展开详情时置顶，覆盖下方节点 */
.node.open:hover{transform:none}            /* 展开后不再因 hover 位移，详情面板稳定 */
.node.s-done{border-color:var(--growth);box-shadow:0 0 0 1px var(--growth-glow),0 0 30px -10px var(--growth-glow)}
.node.s-learning{border-color:var(--bud);box-shadow:0 0 26px -12px var(--bud-glow)}
.node.s-locked{opacity:.6}
.node-top{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;margin-bottom:10px}
.node-name{font-weight:700;font-size:14.5px;line-height:1.25;color:var(--fg)}
.node-cat{font-size:10.5px;color:var(--fg-faint);margin-top:3px;letter-spacing:.01em}
.node-orb{font-size:18px;line-height:1;flex-shrink:0}
.node.s-done .node-orb{filter:drop-shadow(0 0 6px var(--growth-glow))}
.dir-dots{display:flex;gap:3px;margin-top:8px}
.dir-dots i{width:7px;height:7px;border-radius:50%;display:block}
.nbar{height:4px;background:var(--ink);border-radius:4px;overflow:hidden;margin:8px 0 6px}
.nbar > i{display:block;height:100%;border-radius:4px;background:var(--growth);transition:width .5s}
.node.s-learning .nbar > i{background:var(--bud)}
.node.s-locked .nbar > i{background:var(--seed)}
.node.s-locked .nbar > i{opacity:.5}
.ncount{font-size:11.5px;color:var(--fg-faint);font-weight:500}
.ndeps{font-size:10.5px;color:var(--fg-faint);margin-top:4px;opacity:.8}

/* 节点详情抽屉 */
.detail{display:none;margin-top:12px;padding-top:12px;border-top:1px dashed var(--line);min-width:200px}
.node.open .detail{display:block;animation:fadeUp .3s ease both}
@keyframes fadeUp{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.task{display:flex;align-items:flex-start;gap:9px;padding:6px 0;font-size:12.5px;line-height:1.4}
.task input{margin-top:2px;accent-color:var(--growth);cursor:pointer;flex-shrink:0;width:15px;height:15px}
.task label{cursor:pointer;color:var(--fg-dim)}
.task.done label{color:var(--fg-faint);text-decoration:line-through;text-decoration-color:var(--growth)}
/* 验收子任务：缩进挂在对应学习任务下 */
.task.vt{padding-left:20px;font-size:11.5px}
.task.vt label{color:var(--bud)}
.task.vt input{accent-color:var(--bud);width:13px;margin-top:3px}
/* 清单型知识点(有验收)：勾选框禁用淡化，掌握看验收 */
.task.checklist input{opacity:.35;cursor:not-allowed;accent-color:var(--fg-faint)}
.task.checklist label{color:var(--fg-faint)}
.clist{display:inline-block;font-size:9px;font-weight:700;color:var(--bud);background:rgba(251,191,36,.12);border:1px solid rgba(251,191,36,.3);padding:1px 6px;border-radius:8px;margin-right:5px;vertical-align:1px}
.task-group{margin-top:6px}
.task-glabel{display:block;font-size:10.5px;font-weight:700;letter-spacing:.04em;color:var(--fg-faint);margin-bottom:2px;text-transform:uppercase}
.res{font-size:11px;color:var(--growth);text-decoration:none;margin-left:3px;opacity:.85}
.res:hover{opacity:1}

footer{margin-top:64px;text-align:center;color:var(--fg-faint);font-size:12.5px;padding-top:24px;border-top:1px solid var(--line)}
footer code{background:var(--moss);padding:2px 8px;border-radius:6px;color:var(--growth);font-size:11.5px}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""


def tree_accent(tree):
    return tree.get("color", "#4ade80")


def render_overview(trees, ach_results):
    tot_d, tot_t = 0, 0
    for t in trees:
        d, t_, _ = tree_progress(t)
        tot_d += d; tot_t += t_
    total_nodes = sum(len(b.get("nodes", [])) for t in trees for b in t.get("branches", []))
    done_nodes = sum(1 for t in trees for b in t.get("branches", []) for n in b.get("nodes", []) if node_status(n) == "done")
    unlocked = sum(1 for _, ok in ach_results if ok)
    overall = 0 if tot_t == 0 else round(tot_d / tot_t * 100)
    metrics = [
        (f'{overall}<span class="of">%</span>', "整体进度"),
        (f'{tot_d}<span class="of">/{tot_t}</span>', "子任务完成"),
        (f'{done_nodes}<span class="of">/{total_nodes}</span>', "节点点亮"),
        (f'{unlocked}<span class="of">/{len(ach_results)}</span>', "成就绽放"),
    ]
    html = '<div class="dashboard">'
    for v, l in metrics:
        html += f'<div class="metric"><div class="v">{v}</div><div class="l">{l}</div></div>'
    html += '</div>'
    return html


def render_achievements(ach_results):
    html = '<section class="block"><div class="section-title"><h2 class="serif">成就花田</h2><span class="hint">每完成一组目标，便绽放一朵</span></div><div class="bloom-grid">'
    for ach, ok in ach_results:
        cls = "bloom unlocked" if ok else "bloom"
        tier = ach.get("tier", "bronze")
        html += (
            f'<div class="{cls}" title="{escape(ach["desc"])}">'
            f'<span class="petal">{ach["icon"]}</span>'
            f'<span class="meta"><span class="n">{escape(ach["name"])}</span>'
            f'<span class="d">{escape(ach["desc"])}</span></span>'
            f'<span class="tier tier-{tier}">{tier}</span></div>'
        )
    html += '</div></section>'
    return html


def _render_one_task(tk, nid, kind):
    """渲染单个任务。kind='task' 学习知识点 / 'verify' 验收。
    学习知识点若有验收：勾选框置灰禁用(只是清单)，掌握看验收。"""
    tid = tk["id"]
    dcls = " done" if tk.get("done") else ""
    checked = "checked" if tk.get("done") else ""
    res = f'<a class="res" href="{escape(tk["resource"])}" target="_blank" rel="noopener" onclick="event.stopPropagation()">🔗</a>' if tk.get("resource") else ""
    prefix = "🎯 " if kind == "verify" else ""
    # 有验收的学习知识点：勾选框禁用，标题前加「清单」提示
    is_checklist = (kind == "task" and bool(tk.get("verify")))
    cb_attrs = 'disabled' if is_checklist else ''
    cb_cls = ' checklist' if is_checklist else ''
    title_prefix = '<span class="clist">清单</span>' if is_checklist else ''
    return (
        f'<div class="task{dcls}{" vt" if kind=="verify" else ""}{cb_cls}">'
        f'<input type="checkbox" id="tk-{nid}-{tid}" data-key="{nid}/{tid}" {checked} {cb_attrs} onclick="event.stopPropagation();onToggle(this)">'
        f'<label for="tk-{nid}-{tid}">{title_prefix}{prefix}{escape(tk["title"])}</label>{res}</div>'
    )


def _render_task_list(tasks, nid):
    """渲染学习任务列表；每个任务若有 verify 子任务，缩进挂在其下。"""
    out = ""
    for tk in tasks:
        out += _render_one_task(tk, nid, "task")
        for vt in tk.get("verify", []):
            out += _render_one_task(vt, nid, "verify")
    return out


def render_node(nid, info):
    node = info["node"]
    st = node_status(node)
    done, total, pct = node_progress(node)
    orb = {"done": "🍎", "learning": "🌼", "locked": "🌱"}[st]
    # 方向归属色点
    dirs = info.get("dirs", [])
    dots = ""
    if dirs:
        dots = '<div class="dir-dots">' + "".join(
            f'<i style="background:{escape(c)}" title="{escape(did)}"></i>' for (did, c, _) in dirs
        ) + '</div>'
    # 详情：学习任务（验收缩进挂在各自学习任务下）
    detail = _render_task_list(node.get("tasks", []), nid)
    # 兼容旧数据：节点级 verify
    legacy_v = node.get("verify", [])
    if legacy_v:
        detail += '<div class="task-group"><span class="task-glabel">🎯 验收</span>'
        detail += "".join(_render_one_task(vt, nid, "verify") for vt in legacy_v)
        detail += '</div>'
    ptxt = f"{done}/{total} · {pct}%"
    return (
        f'<button class="node s-{st}" data-node="{nid}" data-pct="{pct}" data-done="{done}" data-total="{total}" '
        f'data-top="{info["y"]}" data-left="{info["x"]}" style="left:{info["x"]}px;top:{info["y"]}px" onclick="openNode(this)">'
        f'<div class="node-top"><div><div class="node-name">{escape(node["name"])}</div>'
        f'<div class="node-cat">{escape(node.get("category",""))}</div></div>'
        f'<div class="node-orb">{orb}</div></div>'
        f'<div class="nbar"><i style="width:{pct}%"></i></div>'
        f'<div class="ncount">{ptxt}</div>'
        f'{dots}'
        f'<div class="detail">{detail}</div>'
        f'</button>'
    )


def render_canvas(dag):
    """渲染单张 DAG 画布：绝对定位节点 + 一张 SVG 画所有连线。"""
    layout = dag["layout"]
    nodes_html = "".join(render_node(nid, info) for nid, info in layout.items())
    # 深度刻度（左轴，根/基础在顶）
    axis = '<div class="depth-axis">'
    for d in range(dag["max_depth"] + 1):
        label = "基础" if d == 0 else ("前沿" if d == dag["max_depth"] else str(d))
        axis += f'<span>{label}</span>'
    axis += '</div>'
    return (
        f'<div class="dag-wrap"><div class="dag-canvas" style="width:{dag["canvas_w"]}px;height:{dag["canvas_h"]}px">'
        f'{axis}'
        f'<svg class="edges" width="{dag["canvas_w"]}" height="{dag["canvas_h"]}" viewBox="0 0 {dag["canvas_w"]} {dag["canvas_h"]}" preserveAspectRatio="none"></svg>'
        f'{nodes_html}'
        f'</div></div>'
    )


def render_forest(trees, dag):
    """整仓库一张图。顶部是方向图例 + 全局进度，下方是 DAG 画布。"""
    # 方向图例（颜色 + 名称）
    legend = '<div class="dir-legend">'
    for t in dag["dir_order"]:
        legend += (f'<span class="dir-chip" style="--c:{escape(t.get("color","#4ade80"))}">'
                   f'<i></i>{escape(t.get("icon",""))} {escape(t["title"])}</span>')
    legend += '<span class="dir-hint">· 同色节点归属同一方向，共享节点显多色</span></div>'

    canvas = render_canvas(dag)
    return (
        f'<section class="forest-card">'
        f'<div class="forest-head">{legend}</div>'
        f'{canvas}'
        f'</section>'
    )


HTML_HEAD_TPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} · 实习作战面板</title>
<style>{css}</style>
</head>
<body>
"""


HTML_SCRIPT = r"""
<script>
const STORE_KEY='skilltree_progress_v1';
let store; try{store=JSON.parse(localStorage.getItem(STORE_KEY)||'{}');}catch(e){store={};}
document.querySelectorAll('input[type=checkbox][data-key]').forEach(cb=>{
  const k=cb.dataset.key; if(k in store) cb.checked=store[k];
  syncTask(cb);
});
function onToggle(cb){
  store[cb.dataset.key]=cb.checked;
  localStorage.setItem(STORE_KEY,JSON.stringify(store));
  syncTask(cb); recalc();
}
function syncTask(cb){cb.closest('.task').classList.toggle('done',cb.checked);}

/* ─── 展开避让：一次只开一个节点，下方节点下推，重画连线 ─── */
function openNode(el){
  const canvas=document.querySelector('.dag-canvas'); if(!canvas)return;
  // 单开：先关掉其他 open 节点
  canvas.querySelectorAll('.node.open').forEach(n=>{ if(n!==el) n.classList.remove('open'); });
  el.classList.toggle('open');
  // 等 detail display 生效后再算高度避让
  requestAnimationFrame(()=>layoutAvoid());
}
function layoutAvoid(){
  const canvas=document.querySelector('.dag-canvas'); if(!canvas)return;
  const nodes=[...canvas.querySelectorAll('.node[data-node]')];
  const baseH=parseFloat(canvas.dataset.baseH||canvas.style.height);
  canvas.dataset.baseH=baseH;
  const openEl=canvas.querySelector('.node.open');
  let push=0, openTop=Infinity;
  if(openEl){
    const oTop=parseFloat(openEl.dataset.top);
    // 先把所有节点放回原位，测 open 节点含详情的真实底边
    nodes.forEach(n=>{ n.style.top=n.dataset.top+'px'; });
    const oBottom=oTop+openEl.offsetHeight;
    // 紧邻 open 节点的下一行原顶 = oTop + ROW_GAP；详情溢出行间隙的量即需下推量
    const ROW_GAP=176;
    push=Math.max(0, (oBottom+NODE_GAP)-(oTop+ROW_GAP));
    openTop=oTop;
  }
  // 下方节点(原始 top 严格大于 open 节点 top)整体下推 push，其余归原位
  nodes.forEach(n=>{
    const t=parseFloat(n.dataset.top);
    n.style.top = (push>0 && t>openTop ? t+push : t) + 'px';
  });
  canvas.style.height=(baseH+push)+'px';
  drawEdges();   // 用真实 offsetHeight + 新 top 重画，连线对齐
}

/* 节点级实时进度刷新（按「知识点」掌握度统计） */
function recalc(){
  document.querySelectorAll('.node[data-node]').forEach(el=>{
    // 按渲染顺序解析知识点：每个非 vt 的 .task 是一个知识点，其后紧跟的 .vt 是它的验收
    const rows=[...el.querySelectorAll('.detail .task')];
    let mastered=0,total=0,anyChecked=false;
    let i=0;
    while(i<rows.length){
      const r=rows[i];
      if(r.classList.contains('vt')){ i++; continue; }   // 跳过孤立的验收(不应发生)
      total++;
      const cb=r.querySelector('input[type=checkbox]');
      // 收集本知识点紧跟的验收行
      const verifies=[];
      let j=i+1;
      while(j<rows.length && rows[j].classList.contains('vt')){ verifies.push(rows[j]); j++; }
      const vCbs=verifies.map(v=>v.querySelector('input[type=checkbox]'));
      vCbs.forEach(c=>{if(c&&c.checked)anyChecked=true;});
      if(cb){if(cb.checked)anyChecked=true;}
      // 掌握判定：有验收→验收全勾；无验收→学习任务勾
      let m;
      if(vCbs.length){ m=vCbs.every(c=>c&&c.checked); }
      else { m=cb&&cb.checked; }
      if(m)mastered++;
      i=j;
    }
    const pct=total?Math.round(mastered/total*100):0;
    const st=(total>0&&mastered===total)?'done':(anyChecked?'learning':'locked');
    el.classList.remove('s-done','s-learning','s-locked'); el.classList.add('s-'+st);
    el.dataset.pct=pct; el.dataset.done=mastered; el.dataset.total=total;
    const orb={done:'🍎',learning:'🌼',locked:'🌱'}[st];
    const o=el.querySelector('.node-orb'); if(o)o.textContent=orb;
    const f=el.querySelector('.nbar > i'); if(f)f.style.width=pct+'%';
    const c=el.querySelector('.ncount'); if(c)c.textContent=mastered+'/'+total+' · '+pct+'%';
  });
  drawEdges();   // 进度变化重画边(已完成→高亮绿)
  layoutAvoid(); // 勾选可能改变详情高度，重新避让
}

/* ─── 单画布 DAG 连线：按依赖图连所有边 ─── */
const NODE_W=168, NODE_H=96, NODE_GAP=16;   /* NODE_H: 未展开节点的默认高度(估算); drawEdges 用真实 offsetHeight */
function drawEdges(){
  const svg=document.querySelector('.forest-card .edges');
  const canvas=document.querySelector('.dag-canvas');
  if(!svg||!canvas)return;
  const W=parseFloat(canvas.style.width), H=parseFloat(canvas.style.height);
  svg.setAttribute('viewBox',`0 0 ${W} ${H}`);
  svg.innerHTML='';
  const EDGES=window.__EDGES__||[];          // [[from_id, to_id], ...]
  const nodeOf={};
  canvas.querySelectorAll('.node[data-node]').forEach(el=>{nodeOf[el.dataset.node]=el;});
  EDGES.forEach(([fromId,toId])=>{
    const a=nodeOf[fromId], b=nodeOf[toId];
    if(!a||!b)return;
    // from 是依赖(基础在上·y更小), to 是后续(向下·y更大)
    // from 底端中心 → to 顶端中心；底端用真实高度(展开时也贴实际边)
    const ax=parseFloat(a.style.left)+NODE_W/2;
    const ay=parseFloat(a.style.top)+a.offsetHeight;
    const bx=parseFloat(b.style.left)+NODE_W/2;
    const by=parseFloat(b.style.top);
    // 贝塞尔：控制点拉向垂直方向，形成柔和的枝条
    const cy=(ay+by)/2;
    const d=`M ${ax},${ay} C ${ax},${cy} ${bx},${cy} ${bx},${by}`;
    const path=document.createElementNS('http://www.w3.org/2000/svg','path');
    path.setAttribute('d',d);
    path.setAttribute('data-from',fromId);
    path.setAttribute('data-to',toId);
    // from 节点已完成 → 这段"已走过的路"高亮
    if(a.classList.contains('s-done')) path.classList.add('active');
    else if(a.classList.contains('s-learning')) {} // 默认色
    else path.classList.add('dim');
    svg.appendChild(path);
  });
  // 重画后若处于悬停高亮态，重新应用 onpath 标记
  if(window.__hoverNode) applyHoverPath(window.__hoverNode);
}

/* ─── 悬停高亮学习路径：上游祖先 + 下游后代，其余淡化 ─── */
let _ADJ=null;   // {parents:{id:[...]}, children:{id:[...]}}
function buildAdjacency(){
  if(_ADJ)return _ADJ;
  const parents={},children={};
  (window.__EDGES__||[]).forEach(([f,t])=>{
    (parents[t]=parents[t]||[]).push(f);
    (children[f]=children[f]||[]).push(t);
  });
  return _ADJ={parents,children};
}
function reach(start,graph){
  // BFS 收集所有可达节点（不含 start 自身）
  const seen=new Set(),q=[...graph[start]||[]];
  while(q.length){
    const n=q.shift();
    if(seen.has(n))continue;
    seen.add(n);
    (graph[n]||[]).forEach(m=>q.push(m));
  }
  return seen;
}
function applyHoverPath(nodeId){
  const adj=buildAdjacency();
  const anc=reach(nodeId,adj.parents);          // 上游
  const dec=reach(nodeId,adj.children);          // 下游
  const onpath=new Set([nodeId,...anc,...dec]);
  const canvas=document.querySelector('.dag-canvas'); if(!canvas)return;
  canvas.classList.add('dim');
  // 节点：在路径上的亮，其余淡化
  canvas.querySelectorAll('.node[data-node]').forEach(el=>{
    el.classList.toggle('onpath', onpath.has(el.dataset.node));
  });
  // 边：两端都在路径上才高亮
  canvas.querySelectorAll('.edges path').forEach(p=>{
    const on = onpath.has(p.getAttribute('data-from')) && onpath.has(p.getAttribute('data-to'));
    p.classList.toggle('onpath', on);
  });
}
function clearHover(){
  const canvas=document.querySelector('.dag-canvas'); if(!canvas)return;
  canvas.classList.remove('dim');
  canvas.querySelectorAll('.onpath').forEach(el=>el.classList.remove('onpath'));
}
function bindHover(){
  document.querySelectorAll('.dag-canvas .node[data-node]').forEach(el=>{
    el.addEventListener('mouseenter',()=>{window.__hoverNode=el.dataset.node;applyHoverPath(el.dataset.node);});
    el.addEventListener('mouseleave',()=>{window.__hoverNode=null;clearHover();});
  });
}
window.addEventListener('load',()=>{drawEdges();bindHover();});
window.addEventListener('resize',()=>{drawEdges();});

/* ─── 侧栏路由：hash 切换板块 ─── */
const ROUTES=['tree','profile','templates','fruit'];
function go(route){
  if(!ROUTES.includes(route)) route='tree';
  document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('active', p.id==='panel-'+route));
  document.querySelectorAll('.sb-item').forEach(a=>a.classList.toggle('active', a.dataset.route===route));
  if(route==='tree') setTimeout(drawEdges,30);   // 切回树时重画边
  document.querySelector('.main').scrollTop=0;
}
function currentRoute(){const h=(location.hash||'#tree').slice(1);return ROUTES.includes(h)?h:'tree';}
window.addEventListener('hashchange',()=>go(currentRoute()));
window.addEventListener('load',()=>go(currentRoute()));
document.querySelectorAll('.sb-item').forEach(a=>a.addEventListener('click',e=>{
  // 锚点本身会改 hash，hashchange 会处理；这里只做即时反馈
}));
</script>
"""


# ─────────────────────────── 个人信息 / 模板 / 果实 ───────────────────────────
RESUME_DIR = os.path.join(SKILL_TREE_DIR, "..", "resume")
TEMPLATES_DIR = os.path.join(RESUME_DIR, "templates")
PROFILES_DIR = os.path.join(RESUME_DIR, "profiles")
BUILD_DIR = os.path.join(RESUME_DIR, "build")

# 模板元数据（来自 README 对比表；id = templates/ 下目录名）
TEMPLATE_META = {
    "billryan":    {"name": "Billryan", "style": "中英混合", "lang": "中英文", "scene": "国内大厂", "star": True},
    "sb2nov":      {"name": "sb2nov", "style": "极简单栏", "lang": "英文", "scene": "ATS 投递，外企"},
    "jakegut":     {"name": "Jake Gut", "style": "现代单栏", "lang": "英文", "scene": "科技公司，硅谷风"},
    "hijiangtao": {"name": "hijiangtao", "style": "纯中文", "lang": "中文", "scene": "国内互联网"},
    "luooofan":   {"name": "luooofan", "style": "纯中文", "lang": "中文", "scene": "模块化结构，易维护"},
    "deedy":      {"name": "Deedy", "style": "双栏高密度", "lang": "英文", "scene": "经历多，一页塞满"},
    "awesome-cv": {"name": "Awesome CV", "style": "彩色精致", "lang": "英文", "scene": "视觉美观"},
}


def load_profile():
    p = os.path.join(DATA_DIR, "profile.json")
    if not os.path.exists(p):
        return None
    return load_json(p)


def scan_templates():
    """扫描 resume/templates/ 下的目录，合并 TEMPLATE_META。"""
    out = []
    if not os.path.isdir(TEMPLATES_DIR):
        return out
    for d in sorted(os.listdir(TEMPLATES_DIR)):
        full = os.path.join(TEMPLATES_DIR, d)
        if not os.path.isdir(full):
            continue
        meta = TEMPLATE_META.get(d, {"name": d, "style": "—", "lang": "—", "scene": "—"})
        meta = dict(meta)
        meta["id"] = d
        meta["path"] = "../../resume/templates/%s/" % d
        out.append(meta)
    return out


def scan_fruits(trees):
    """扫描 resume/profiles/ + resume/build/*.pdf，生成果实卡片数据。"""
    out = []
    if not os.path.isdir(PROFILES_DIR):
        return out
    tree_by_id = {t["tree_id"]: t for t in trees}
    for d in sorted(os.listdir(PROFILES_DIR)):
        pdir = os.path.join(PROFILES_DIR, d)
        if not os.path.isdir(pdir):
            continue
        pdf = os.path.join(BUILD_DIR, "%s.pdf" % d)
        has_pdf = os.path.exists(pdf)
        tree = tree_by_id.get(d)
        out.append({
            "id": d,
            "title": tree["title"] if tree else d,
            "icon": tree.get("icon", "📄") if tree else "📄",
            "subtitle": tree.get("subtitle", "") if tree else "",
            "color": tree.get("color", "#4ade80") if tree else "#4ade80",
            "pct": tree_progress(tree)[2] if tree else 0,
            "has_pdf": has_pdf,
            "pdf_path": "../../resume/build/%s.pdf" % d if has_pdf else None,
            "profile_path": "../../resume/profiles/%s/" % d,
        })
    return out


def render_panel_profile(profile):
    if not profile:
        return '<div class="panel"><div class="empty">未找到 data/profile.json</div></div>'
    # 联系方式
    c = profile.get("contact", {})
    contact_items = []
    if c.get("email"):
        contact_items.append(f'<span class="ci">✉ <a href="mailto:{escape(c["email"])}">{escape(c["email"])}</a></span>')
    if c.get("phone"):
        contact_items.append(f'<span class="ci">☎ {escape(c["phone"])}</span>')
    if c.get("github"):
        contact_items.append(f'<span class="ci">⌥ <a href="{escape(c.get("github_url","#"))}" target="_blank" rel="noopener">{escape(c["github"])}</a></span>')
    contact_html = '<div class="contact-row">' + "".join(contact_items) + '</div>'

    # 教育
    edu_html = ""
    for e in profile.get("education", []):
        edu_html += (
            f'<div class="edu-item"><div class="edu-main"><span class="edu-school">{escape(e["school"])}</span>'
            f'<span class="edu-degree">{escape(e.get("degree",""))} · {escape(e.get("major",""))}</span></div>'
            f'<span class="edu-period">{escape(e.get("period",""))}</span></div>'
        )

    # 技能
    skill_html = ""
    for s in profile.get("skills", []):
        chips = "".join(f'<span class="chip">{escape(i)}</span>' for i in s.get("items", []))
        skill_html += f'<div class="skill-row"><span class="skill-group">{escape(s["group"])}</span><div class="chips">{chips}</div></div>'

    # 经历
    exp_html = ""
    for x in profile.get("experience", []):
        tech = "".join(f'<span class="chip sm">{escape(t)}</span>' for t in x.get("tech", []))
        hl = "".join(f'<li>{escape(h)}</li>' for h in x.get("highlights", []))
        url = x.get("url")
        link = f'<a class="exp-link" href="{escape(url)}" target="_blank" rel="noopener">GitHub ↗</a>' if url else ""
        exp_html += (
            f'<div class="exp-card"><div class="exp-head"><div><div class="exp-title">{escape(x["title"])}</div>'
            f'<div class="exp-role">{escape(x.get("role",""))}</div></div><span class="exp-period">{escape(x.get("period",""))}</span></div>'
            f'<div class="chips">{tech}</div>'
            f'<p class="exp-desc">{escape(x.get("desc",""))}</p>'
            f'{"<ul class=\"exp-hl\">" + hl + "</ul>" if hl else ""}{link}</div>'
        )

    # 获奖
    award_html = ""
    for a in profile.get("awards", []):
        note = f' <span class="award-note">{escape(a["note"])}</span>' if a.get("note") else ""
        award_html += f'<div class="award-item"><span class="award-year">{escape(str(a.get("year","")))}</span><span class="award-title">{escape(a["title"])}{note}</span></div>'

    # 学生工作
    lead_html = "".join(f'<li>{escape(l)}</li>' for l in profile.get("leadership", []))

    name = escape(profile.get("name", ""))
    name_en = escape(profile.get("name_en", ""))
    tagline = escape(profile.get("tagline", ""))
    return f'''
    <section class="panel" id="panel-profile">
      <div class="panel-head">
        <h2 class="serif panel-title">{name} <span class="name-en">{name_en}</span></h2>
        <p class="panel-sub">{tagline}</p>
        {contact_html}
      </div>
      <div class="pgrid">
        <div class="pcol">
          <h3 class="psec">教育背景</h3>
          {edu_html}
          <h3 class="psec">技能</h3>
          {skill_html}
        </div>
        <div class="pcol">
          <h3 class="psec">项目经历</h3>
          {exp_html}
        </div>
      </div>
      <div class="pgrid">
        <div class="pcol"><h3 class="psec">竞赛获奖</h3>{award_html}</div>
        <div class="pcol"><h3 class="psec">学生工作</h3><ul class="lead-list">{lead_html}</ul></div>
      </div>
    </section>'''


def render_panel_templates(templates):
    cards = ""
    for t in templates:
        star = '<span class="tstar">★ 当前在用</span>' if t.get("star") else ""
        cards += (
            f'<a class="tcard" href="{escape(t["path"])}" target="_blank" rel="noopener">'
            f'<div class="tcard-top"><span class="tname serif">{escape(t["name"])}</span>{star}</div>'
            f'<div class="tmeta"><span>{escape(t["style"])}</span><span>·</span><span>{escape(t["lang"])}</span></div>'
            f'<div class="tscene">{escape(t["scene"])}</div>'
            f'<div class="tcard-cta">查看模板 →</div></a>'
        )
    return f'''
    <section class="panel" id="panel-templates">
      <div class="panel-head"><h2 class="serif panel-title">简历模板</h2>
      <p class="panel-sub">{len(templates)} 套 LaTeX 模板 · 点卡片进入模板目录</p></div>
      <div class="tcard-grid">{cards}</div>
    </section>'''


def render_panel_fruit(fruits):
    cards = ""
    for f in fruits:
        status = "已编译" if f["has_pdf"] else "未编译"
        stcls = "ok" if f["has_pdf"] else "no"
        btn = (f'<a class="fbtn primary" href="{escape(f["pdf_path"])}" target="_blank" rel="noopener">📄 打开 PDF</a>'
               if f["has_pdf"] else
               '<span class="fbtn disabled">未编译</span>')
        cards += (
            f'<div class="fcard" style="--c:{escape(f["color"])}">'
            f'<div class="fcard-top"><span class="fico">{f["icon"]}</span>'
            f'<span class="fstatus {stcls}">{status}</span></div>'
            f'<div class="fname serif">{escape(f["title"])}</div>'
            f'<div class="fsub">{escape(f["subtitle"])}</div>'
            f'<div class="fbar"><i style="width:{f["pct"]}%"></i></div>'
            f'<div class="fpct">技能进度 {f["pct"]}%</div>'
            f'<div class="fbtns">{btn}'
            f'<a class="fbtn" href="{escape(f["profile_path"])}" target="_blank" rel="noopener">源码</a></div>'
            f'</div>'
        )
    return f'''
    <section class="panel" id="panel-fruit">
      <div class="panel-head"><h2 class="serif panel-title">🍎 果实 · 简历成品</h2>
      <p class="panel-sub">技能树结出的果实 · 点「打开 PDF」在新标签查看编译好的简历</p></div>
      <div class="fcard-grid">{cards}</div>
    </section>'''


def render_html(trees, ach_results):
    dag = compute_dag_layout(trees)
    profile = load_profile()
    templates = scan_templates()
    fruits = scan_fruits(trees)
    title = "实习作战面板"

    # 整体进度（侧栏用）
    tot_d, tot_t = 0, 0
    for t in trees:
        d, t_, _ = tree_progress(t); tot_d += d; tot_t += t_
    overall = 0 if tot_t == 0 else round(tot_d / tot_t * 100)
    unlocked = sum(1 for _, ok in ach_results if ok)

    html = HTML_HEAD_TPL.format(title=escape(title), css=CSS)

    # ── 侧栏 ──
    pname = escape(profile["name"]) if profile else "实习生"
    ptag = escape(profile.get("tagline", "")) if profile else ""
    html += f'''
<div class="app">
  <aside class="sidebar">
    <div class="sb-brand">
      <div class="sb-logo">🌳</div>
      <div class="sb-name serif">{pname}</div>
      <div class="sb-tag">{ptag}</div>
    </div>
    <nav class="sb-nav">
      <a class="sb-item active" data-route="tree" href="#tree"><span class="sb-ico">🌳</span><span>技能树</span></a>
      <a class="sb-item" data-route="profile" href="#profile"><span class="sb-ico">👤</span><span>个人信息</span></a>
      <a class="sb-item" data-route="templates" href="#templates"><span class="sb-ico">📄</span><span>简历模板</span></a>
      <a class="sb-item" data-route="fruit" href="#fruit"><span class="sb-ico">🍎</span><span>果实展示</span></a>
    </nav>
    <div class="sb-foot">
      <div class="sb-prog-ring">
        <svg viewBox="0 0 60 60"><circle class="ring-bg" cx="30" cy="30" r="26"/><circle class="ring-fg" cx="30" cy="30" r="26" style="stroke-dashoffset:{26*2*3.14159*(1-overall/100):.1f}"/></svg>
        <span class="ring-txt">{overall}%</span>
      </div>
      <div class="sb-stats"><b>{unlocked}</b> 成就 · <b>{tot_d}/{tot_t}</b> 任务</div>
    </div>
  </aside>
  <main class="main">'''

    # ── 板块 1: 技能树（基础在上）──
    html += '<section class="panel active" id="panel-tree">'
    html += '<div class="panel-head"><h2 class="serif panel-title">知识图谱</h2>'
    html += '<p class="panel-sub">所有方向汇于一棵树 · <b>基础在上，向下生长</b> · 按依赖关系连线</p></div>'
    html += render_overview(trees, ach_results)
    html += '<div class="dag-block">' + render_forest(trees, dag) + '</div>'
    html += render_achievements(ach_results)
    html += '</section>'

    # ── 板块 2-4 ──
    html += render_panel_profile(profile)
    html += render_panel_templates(templates)
    html += render_panel_fruit(fruits)

    html += f'<footer class="app-foot">改 <code>skill-tree/data/*.json</code> 后重跑 <code>python skill-tree/tools/render.py</code> · 进度保存在浏览器本地</footer>'
    html += '</main></div>'
    # 注入依赖边列表 + 路由脚本
    html += f'<script>window.__EDGES__={json.dumps(dag["edges"], ensure_ascii=False)};</script>'
    html += HTML_SCRIPT
    html += "</body></html>"
    return html


# ─────────────────────────── Markdown 渲染（保持稳定）───────────────────────────
def render_markdown(trees, ach_results):
    L = []
    L.append("# 🌳 实习技能树 · 进度总览\n")
    L.append("> 数据源：`skill-tree/data/*.json` · 由 `tools/render.py` 生成 · 请勿手改本文件\n")
    tot_d, tot_t = 0, 0
    for t in trees:
        d, t_, _ = tree_progress(t); tot_d += d; tot_t += t_
    unlocked = sum(1 for _, ok in ach_results if ok)
    total_nodes = sum(len(b.get("nodes", [])) for t in trees for b in t.get("branches", []))
    done_nodes = sum(1 for t in trees for b in t.get("branches", []) for n in b.get("nodes", []) if node_status(n) == "done")
    L.append("## 总览\n")
    L.append(f"- 整体进度：**{0 if tot_t==0 else round(tot_d/tot_t*100)}%**")
    L.append(f"- 子任务：**{tot_d} / {tot_t}** 完成")
    L.append(f"- 节点点亮：**{done_nodes} / {total_nodes}**")
    L.append(f"- 成就绽放：**{unlocked} / {len(ach_results)}**")
    L.append(f"- 技能树：**{len(trees)}** 棵\n")

    L.append("## 各方向进度\n")
    L.append("| 方向 | 分支 | 进度 | 完成/总数 |")
    L.append("|------|------|------|-----------|")
    for t in trees:
        td, tt, tpct = tree_progress(t)
        bar = "█" * (tpct // 10) + "░" * (10 - tpct // 10)
        L.append(f"| {t.get('icon','')} {t['title']} | **全部** | {bar} {tpct}% | {td}/{tt} |")
        for b in t.get("branches", []):
            bd, bt, bpct = branch_progress(b)
            shared = " 🔗共享" if b.get("shared") else ""
            L.append(f"| | {b.get('icon','')} {b['name']}{shared} | {bpct}% | {bd}/{bt} |")
    L.append("")

    for t in trees:
        L.append(f"## {t.get('icon','')} {t['title']} — {t.get('subtitle','')}\n")
        fruit = t.get("fruit", "")
        if fruit:
            L.append(f"🍎 果实(简历)：[{fruit}]({fruit})\n")
        for b in t.get("branches", []):
            bd, bt, bpct = branch_progress(b)
            L.append(f"### {b.get('icon','')} {b['name']} — {bpct}% ({bd}/{bt})")
            if b.get("description"):
                L.append(f"> {b['description']}\n")
            L.append("| 节点 | 状态 | 掌握度 | 知识点 |")
            L.append("|------|------|--------|--------|")
            for n in b.get("nodes", []):
                st = node_status(n)
                nd, nt, _ = node_progress(n)
                sttxt = {"done": "✅ 已完成", "learning": "🔄 学习中", "locked": "🔒 未解锁"}[st]
                parts = []
                for tk in n.get("tasks", []):
                    ver = tk.get("verify", [])
                    if ver:
                        # 清单型知识点：掌握看验收
                        allV = all(v.get("done") for v in ver)
                        parts.append(f"{'✅' if allV else '⬜'} {tk['title']} <sub>(清单)</sub>")
                        for vt in ver:
                            vmark = "🎯✅" if vt.get("done") else "🎯⬜"
                            parts.append(f"&nbsp;&nbsp;{vmark} {vt['title']}")
                    else:
                        mark = "✅" if tk.get("done") else "⬜"
                        parts.append(f"{mark} {tk['title']}")
                taskcell = "<br>".join(parts) if parts else "—"
                L.append(f"| **{n['name']}** | {sttxt} | {nd}/{nt} | {taskcell} |")
            L.append("")

    L.append("## 🏆 成就\n")
    L.append("| 状态 | 成就 | 描述 | 等级 |")
    L.append("|------|------|------|------|")
    for ach, ok in ach_results:
        mark = "✅" if ok else "🔒"
        tier = {"gold": "🥇金", "silver": "🥈银", "bronze": "🥉铜"}.get(ach.get("tier"), "")
        L.append(f"| {mark} | {ach['icon']} {ach['name']} | {ach['desc']} | {tier} |")
    return "\n".join(L) + "\n"


def main():
    trees, achievements = load_all()
    if not trees:
        print("[render] 未在 data/ 找到技能树 JSON，退出。", file=sys.stderr)
        sys.exit(1)
    os.makedirs(DIST_DIR, exist_ok=True)
    ach_results = evaluate_achievements(trees, achievements)

    html = render_html(trees, ach_results)
    with open(os.path.join(DIST_DIR, "skill-tree.html"), "w", encoding="utf-8") as f:
        f.write(html)
    md = render_markdown(trees, ach_results)
    with open(os.path.join(DIST_DIR, "PROGRESS.md"), "w", encoding="utf-8") as f:
        f.write(md)

    print("✅ 技能树生成完成")
    for t in trees:
        d, tt, pct = tree_progress(t)
        print(f"   {t.get('icon','')} {t['title']:<8} {d}/{tt} ({pct}%)")
    unlocked = sum(1 for _, ok in ach_results if ok)
    print(f"   🏆 成就解锁 {unlocked}/{len(ach_results)}")


if __name__ == "__main__":
    main()
