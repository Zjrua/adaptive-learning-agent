# tests/test_loop.py
from __future__ import annotations

from agent.loop import run_agent, parse_react
from agent.tool_runtime import Context
from tests.fakes import FakeChat


def _ctx(graph=None):
    return Context(uid="u", graph=graph or {"nodes": [], "overview": {}},
                   resume=None, retriever=None, rag_index_dir=None)


def test_parse_react_tool_step():
    text = "Thought: 要查进度\nAction: get_progress\nArguments: {}"
    step = parse_react(text)
    assert step["type"] == "tool"
    assert step["action"] == "get_progress"


def test_parse_react_final_answer():
    text = "Thought: 够了\nFinal Answer: 建议学 DCN。"
    step = parse_react(text)
    assert step["type"] == "final"
    assert "DCN" in step["answer"]


def test_parse_react_garbage_returns_final():
    step = parse_react("乱七八糟没有格式")
    assert step["type"] == "final"


def test_loop_chat_intent_short_circuits():
    """Planner 判 chat → 直接走 Executor 一步，不进多步 ReAct。"""
    fake = FakeChat([
        {"content": '{"intent":"chat","sub_tasks":[],"needs_doc":false}', "tool_calls": []},
        {"content": "Thought: 闲聊\nFinal Answer: 你好！加油学算法！", "tool_calls": []},
    ])
    ctx = _ctx()
    events = list(run_agent(ctx, "你好", chat_fn=fake, cfg={"base_url": "x", "api_key": "y"}))
    types = [e["type"] for e in events]
    assert "thinking" in types
    assert "final_answer" in types
    assert any("加油" in e.get("content", "") for e in events if e["type"] == "final_answer")
    assert "done" in types


def test_loop_tool_step_then_final():
    fake = FakeChat([
        {"content": '{"intent":"query","sub_tasks":[],"needs_doc":false}', "tool_calls": []},
        {"content": "Thought: 查进度\nAction: get_progress\nArguments: {}", "tool_calls": []},
        {"content": "Thought: 好了\nFinal Answer: 你整体 45%。", "tool_calls": []},
    ])
    ctx = _ctx(graph={"nodes": [], "overview": {"overall_pct": 45, "mastered_points": 0, "total_points": 0}})
    events = list(run_agent(ctx, "我学到哪了", chat_fn=fake, cfg={"base_url": "x", "api_key": "y"}))
    assert any(e["type"] == "tool_call" and e["action"] == "get_progress" for e in events)
    assert any(e["type"] == "tool_result" for e in events)
    assert any(e["type"] == "final_answer" for e in events)


def test_loop_max_steps_guard():
    """连续返回工具调用不收敛时，应被最大步数截断，产出降级 final。"""
    tool_only = {"content": "Thought: 继续\nAction: get_progress\nArguments: {}", "tool_calls": []}
    fake = FakeChat([
        {"content": '{"intent":"query","sub_tasks":[],"needs_doc":false}', "tool_calls": []},
        tool_only, tool_only, tool_only, tool_only, tool_only, tool_only,
    ])
    ctx = _ctx()
    events = list(run_agent(ctx, "x", chat_fn=fake, cfg={"base_url": "x", "api_key": "y"}, max_steps=4))
    assert any(e["type"] == "final_answer" for e in events)  # 被截断后仍有 final


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
