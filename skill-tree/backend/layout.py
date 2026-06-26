"""layout.py — DAG 布局（纯函数，从 render.py 移植）。

合并所有方向的节点去重 → 按 depends_on 拓扑分层 → 算 x/y 坐标。
基础(depth 0)在上，向下生长。
"""
from __future__ import annotations
from typing import Any

# 布局常量（前端 Node.tsx 必须与之保持一致：卡片宽/行距/列距）
NODE_W = 180
NODE_H = 92
COL_GAP = 28
ROW_GAP = 148
CANVAS_PAD = 48


def _branch_leaf(branch: dict) -> str | None:
    nodes = branch.get("nodes", [])
    ids = {n["id"] for n in nodes}
    depended = set()
    for n in nodes:
        for d in n.get("depends_on", []):
            if d in ids:
                depended.add(d)
    leaves = [n["id"] for n in nodes if n["id"] not in depended]
    return leaves[-1] if leaves else (nodes[-1]["id"] if nodes else None)


def merge_nodes(trees: list[dict]) -> tuple[dict, dict, list[dict], dict]:
    """返回 (nodes_by_id, dirs_by_id, dir_order, branch_index)。"""
    nodes_by_id: dict[str, dict] = {}
    dirs_by_id: dict[str, list[tuple[str, str, str]]] = {}
    dir_order: list[dict] = []
    branch_index: dict[str, tuple[dict, dict]] = {}
    for t in trees:
        dir_order.append(t)
        for b in t.get("branches", []):
            branch_index[b["id"]] = (t, b)
            for n in b.get("nodes", []):
                nid = n["id"]
                entry = (t["tree_id"], t.get("color", "#4ade80"), b["id"])
                dirs_by_id.setdefault(nid, [])
                if not any(e[0] == entry[0] for e in dirs_by_id[nid]):
                    dirs_by_id[nid].append(entry)
                if nid not in nodes_by_id:
                    nodes_by_id[nid] = n
                else:
                    if len(n.get("tasks", [])) > len(nodes_by_id[nid].get("tasks", [])):
                        nodes_by_id[nid] = n
    return nodes_by_id, dirs_by_id, dir_order, branch_index


def normalize_deps(nodes_by_id: dict, branch_index: dict) -> dict[str, list[str]]:
    branch_leaf = {bid: _branch_leaf(b) for bid, (_, b) in branch_index.items()}
    all_ids = set(nodes_by_id)
    norm: dict[str, list[str]] = {}
    for nid, node in nodes_by_id.items():
        resolved: list[str] = []
        seen: set[str] = set()
        for d in node.get("depends_on", []):
            tgt = None
            if d in all_ids:
                tgt = d
            elif d in branch_leaf and branch_leaf[d] and branch_leaf[d] in all_ids:
                tgt = branch_leaf[d]
            if tgt and tgt not in seen:
                seen.add(tgt)
                resolved.append(tgt)
        norm[nid] = resolved
    return norm


def compute_depths(deps: dict[str, list[str]]) -> dict[str, int]:
    depth: dict[str, int] = {}

    def dpt(nid: str, stack: set[str]) -> int:
        if nid in depth:
            return depth[nid]
        if nid in stack:
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


def compute_layout(trees: list[dict]) -> dict:
    """返回 {nodes, edges, canvas, dir_order}。基础在上。"""
    nodes_by_id, dirs_by_id, dir_order, branch_index = merge_nodes(trees)
    deps = normalize_deps(nodes_by_id, branch_index)
    depth = compute_depths(deps)

    dir_rank = {t["tree_id"]: i for i, t in enumerate(dir_order)}
    branch_rank: dict[tuple[str, str], int] = {}
    for t in dir_order:
        for i, b in enumerate(t.get("branches", [])):
            branch_rank[(t["tree_id"], b["id"])] = i
    node_seq: dict[str, int] = {}
    seq = 0
    for t in dir_order:
        for b in t.get("branches", []):
            for n in b.get("nodes", []):
                if n["id"] not in node_seq:
                    node_seq[n["id"]] = seq
                    seq += 1

    def sort_key(nid: str) -> tuple[int, int, int]:
        dirs = dirs_by_id.get(nid, [])
        primary = dir_rank.get(dirs[0][0], 99) if dirs else 99
        brank = branch_rank.get((dirs[0][0], dirs[0][2]), 99) if dirs else 99
        return (primary, brank, node_seq.get(nid, 999))

    max_depth = max(depth.values()) if depth else 0
    rows: dict[int, list[str]] = {d: [] for d in range(max_depth + 1)}
    for nid in nodes_by_id:
        rows[depth[nid]].append(nid)
    for d in rows:
        rows[d].sort(key=sort_key)

    canvas_h = (max_depth + 1) * ROW_GAP + CANVAS_PAD * 2
    max_row_w = 0
    pos: dict[str, dict] = {}
    for d, ids in rows.items():
        n = len(ids)
        row_w = n * NODE_W + (n - 1) * COL_GAP if n > 0 else 0
        max_row_w = max(max_row_w, row_w)
        y = CANVAS_PAD + d * ROW_GAP
        for i, nid in enumerate(ids):
            x = CANVAS_PAD + i * (NODE_W + COL_GAP)
            pos[nid] = {"x": x, "y": y, "depth": d}
    canvas_w = max_row_w + CANVAS_PAD * 2

    edges = []
    for nid, ds in deps.items():
        for d in ds:
            edges.append({"from": d, "to": nid})

    nodes_out = []
    for nid, node in nodes_by_id.items():
        nodes_out.append({
            "id": nid,
            "name": node["name"],
            "category": node.get("category", ""),
            "tasks": node.get("tasks", []),
            "status_hint": node.get("status", "locked"),
            "depends_on": deps[nid],
            "x": pos[nid]["x"],
            "y": pos[nid]["y"],
            "depth": pos[nid]["depth"],
            "dirs": [{"id": d, "color": c, "branch": br} for (d, c, br) in dirs_by_id.get(nid, [])],
        })

    return {
        "nodes": nodes_out,
        "edges": edges,
        "canvas": {"w": canvas_w, "h": canvas_h},
        "dir_order": [{"id": t["tree_id"], "title": t["title"], "icon": t.get("icon", ""),
                       "color": t.get("color", "#4ade80"), "subtitle": t.get("subtitle", "")} for t in dir_order],
        "constants": {"NODE_W": NODE_W, "NODE_H": NODE_H, "COL_GAP": COL_GAP, "ROW_GAP": ROW_GAP, "CANVAS_PAD": CANVAS_PAD},
    }
