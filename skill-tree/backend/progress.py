"""progress.py — 掌握度计算（纯函数，从 render.py 移植）。

核心语义：以「知识点」为单位算掌握度。一个学习任务 = 一个知识点。
- 有 verify 的知识点：所有验收 done 才算掌握（学习任务勾选不计）
- 无 verify 的知识点：学习任务 done 即掌握
"""
from __future__ import annotations
from typing import Any

Node = dict[str, Any]
Task = dict[str, Any]


def point_mastered(task: Task) -> bool:
    """一个知识点(学习任务)是否掌握。"""
    ver = task.get("verify", [])
    if ver:
        return all(v.get("done") for v in ver)
    return bool(task.get("done"))


def node_mastery(node: Node) -> tuple[int, int, int]:
    """返回 (mastered, total_points, pct)。"""
    points = node.get("tasks", [])
    total = len(points)
    mastered = sum(1 for tk in points if point_mastered(tk))
    pct = 100 if total == 0 else round(mastered / total * 100)
    return mastered, total, pct


def node_status(node: Node) -> str:
    """done | learning | locked。"""
    mastered, total, _ = node_mastery(node)
    if total > 0 and mastered == total:
        return "done"
    if total == 0 and node.get("status") == "done":
        return "done"
    # 有任何勾选进展 → learning
    if any(_any_done(node)) or node.get("status") in ("learning", "done"):
        return "learning"
    return "locked"


def _any_done(node: Node) -> list[bool]:
    """节点里所有勾选项的 done 列表（学习任务 + 各自验收）。"""
    out: list[bool] = []
    for tk in node.get("tasks", []):
        out.append(bool(tk.get("done")))
        out.extend(bool(v.get("done")) for v in tk.get("verify", []))
    return out


def branch_progress(branch: dict) -> tuple[int, int, int]:
    tot_m, tot_t = 0, 0
    for n in branch.get("nodes", []):
        m, t, _ = node_mastery(n)
        tot_m += m
        tot_t += t
    pct = 0 if tot_t == 0 else round(tot_m / tot_t * 100)
    return tot_m, tot_t, pct


def tree_progress(branches: list[dict]) -> tuple[int, int, int]:
    tot_m, tot_t = 0, 0
    for b in branches:
        m, t, _ = branch_progress(b)
        tot_m += m
        tot_t += t
    pct = 0 if tot_t == 0 else round(tot_m / tot_t * 100)
    return tot_m, tot_t, pct


def evaluate_achievements(trees: list[dict], achievements: dict) -> list[tuple[dict, bool]]:
    """返回 [(achievement, unlocked), ...]。从 render.py 移植。"""
    node_idx: dict[str, Node] = {}
    for t in trees:
        for b in t.get("branches", []):
            for n in b.get("nodes", []):
                node_idx[n["id"]] = n

    tree_pcts = {t["tree_id"]: tree_progress(t.get("branches", []))[2] for t in trees}
    total_points = sum(len(n.get("tasks", [])) for n in node_idx.values())
    mastered_points = sum(node_mastery(n)[0] for n in node_idx.values())
    done_nodes = sum(1 for n in node_idx.values() if node_status(n) == "done")
    # 所有勾选 done 的项（任务+验收）
    all_done_items = sum(sum(_any_done(n)) for n in node_idx.values())

    results = []
    for ach in achievements.get("achievements", []):
        cond = ach["condition"]
        ct = cond["type"]
        ok = False
        if ct == "nodes_done":
            ok = done_nodes >= cond["min"]
        elif ct == "points_mastered":
            ok = mastered_points >= cond["min"]
        elif ct == "tasks_done":           # 兼容：按勾选项数
            ok = all_done_items >= cond["min"]
        elif ct == "tree_progress":
            ok = any(p >= cond["min"] for p in tree_pcts.values())
        elif ct == "all_trees_progress":
            ok = bool(tree_pcts) and all(p >= cond["min"] for p in tree_pcts.values())
        elif ct == "branch_done":
            tid = cond.get("tree_id")
            bid = cond["branch_id"]
            for t in trees:
                if tid and t["tree_id"] != tid:
                    continue
                for b in t.get("branches", []):
                    if b["id"] == bid and b.get("nodes") and all(node_status(n) == "done" for n in b["nodes"]):
                        ok = True
        results.append((ach, ok))
    return results
