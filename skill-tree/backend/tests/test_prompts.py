# tests/test_prompts.py
from __future__ import annotations

from agent.prompts import SYS_PLANNER, SYS_EXECUTOR, SYS_WRITER, render_planner, render_executor


def test_planner_template_has_intent_categories():
    for intent in ['"chat"', '"query"', '"mutate"', '"produce"']:
        assert intent in SYS_PLANNER


def test_executor_template_has_react_format():
    assert "Thought" in SYS_EXECUTOR
    assert "Action" in SYS_EXECUTOR
    assert "Final Answer" in SYS_EXECUTOR


def test_writer_template_has_doc_types():
    for t in ["学习笔记", "复习卡", "周报"]:
        assert t in SYS_WRITER


def test_render_planner_injects_inputs():
    p = render_planner(progress_summary="整体45%", user_input="下一步学啥")
    assert "整体45%" in p
    assert "下一步学啥" in p


def test_render_executor_injects_tools_and_graph():
    p = render_executor(tools_text="- get_progress(): 查进度",
                        graph_summary="节点: deepfm(learning)")
    assert "get_progress" in p
    assert "deepfm" in p


from agent.prompts import SYS_CHAT_DIRECT, SYS_REFLECT, render_chat_direct, render_reflect


def test_executor_has_few_shot_examples():
    """Executor prompt 含 ReAct 示例。"""
    assert "示例" in SYS_EXECUTOR or "Example" in SYS_EXECUTOR or "例子" in SYS_EXECUTOR


def test_planner_has_few_shot_examples():
    assert "示例" in SYS_PLANNER or "Example" in SYS_PLANNER


def test_chat_direct_template_exists():
    assert "直接回答" in SYS_CHAT_DIRECT or "直接给" in SYS_CHAT_DIRECT


def test_reflect_template_outputs_json():
    assert '"ok"' in SYS_REFLECT and '"gap"' in SYS_REFLECT


def test_render_chat_direct_injects():
    p = render_chat_direct(history_summary="之前聊了 DCN")
    assert "DCN" in p


def test_render_reflect_injects():
    p = render_reflect(question="下一步学啥", observations="整体45%",
                       draft="建议学 DCN")
    assert "下一步学啥" in p
    assert "DCN" in p
