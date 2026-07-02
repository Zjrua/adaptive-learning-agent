from __future__ import annotations
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


def test_apply_node_defaults_to_first_branch_when_branch_id_none():
    tree = _seed_tree()
    node = {"id": "dcn", "name": "DCN", "tasks": []}
    main._apply_node_to_tree(tree, node, branch_id=None)
    ids = [n["id"] for b in tree["branches"] for n in b["nodes"]]
    assert "dcn" in ids


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


def test_apply_tasks_missing_node_returns_false():
    tree = _seed_tree()
    assert main._apply_tasks_to_node(tree, "nope", [{"id": "x", "title": "x"}]) is False
