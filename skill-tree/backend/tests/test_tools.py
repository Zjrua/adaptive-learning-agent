# tests/test_tools.py
from __future__ import annotations

from agent.tools import TOOLS_EXECUTOR, TOOLS_WRITER, tool_schema_text


def test_executor_tools_contain_core_set():
    names = {t["name"] for t in TOOLS_EXECUTOR}
    for must in {"get_progress", "get_node", "get_next", "search_knowledge",
                 "add_node", "add_tasks", "toggle_task"}:
        assert must in names, f"缺工具: {must}"


def test_writer_tools_only_doc():
    names = {t["name"] for t in TOOLS_WRITER}
    assert "write_doc" in names
    assert "add_node" not in names  # Writer 不该有图谱写工具


def test_tool_schema_text_contains_name_and_description():
    txt = tool_schema_text(TOOLS_EXECUTOR)
    assert "get_progress" in txt
    assert "掌握度" in txt or "进度" in txt


def test_each_tool_has_valid_schema():
    for t in TOOLS_EXECUTOR + TOOLS_WRITER:
        assert t["name"]
        assert t["description"]
        assert t["parameters"]["type"] == "object"
