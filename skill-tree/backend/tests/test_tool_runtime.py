# tests/test_tool_runtime.py
from __future__ import annotations

from agent.tool_runtime import Context, execute_tool, ToolError


def _ctx(graph=None, resume=None, retriever=None):
    return Context(uid="u", graph=graph or {}, resume=resume,
                   retriever=retriever, rag_index_dir=None)


def test_get_progress_from_graph():
    graph = {"nodes": [{"id": "deepfm", "name": "DeepFM", "state": "learning", "pct": 50,
                        "mastered": 2, "total_points": 4}],
             "overview": {"overall_pct": 45}}
    out = execute_tool("get_progress", {}, _ctx(graph=graph))
    assert "45" in out
    assert "deepfm" in out or "DeepFM" in out


def test_get_node_missing_returns_hint():
    out = execute_tool("get_node", {"node_id": "nope"}, _ctx(graph={"nodes": []}))
    assert "nope" in out


def test_unknown_tool_raises():
    try:
        execute_tool("bogus", {}, _ctx())
        assert False, "应抛 ToolError"
    except ToolError:
        pass


def test_add_node_returns_proposal_not_written():
    """add_node 不直接写盘，返回"建议"标记。"""
    out = execute_tool("add_node", {"description": "LightGCN"}, _ctx())
    assert "建议" in out or "proposal" in out.lower()
