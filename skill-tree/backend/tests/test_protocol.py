# tests/test_protocol.py
from __future__ import annotations
import json

from agent.protocol import ToolCall, parse_directive, to_tool_schemas, normalize_tool_calls


def test_parse_directive_single():
    text = '好的，我需要查进度。\n<tool_call>{"name":"get_progress","arguments":{}}</tool_call>\n'
    calls = parse_directive(text)
    assert len(calls) == 1
    assert calls[0].name == "get_progress"
    assert calls[0].arguments == {}


def test_parse_directive_with_args():
    text = '<tool_call>{"name":"search_knowledge","arguments":{"query":"deepfm","top_k":3}}</tool_call>'
    calls = parse_directive(text)
    assert calls[0].name == "search_knowledge"
    assert calls[0].arguments["top_k"] == 3


def test_parse_directive_none():
    assert parse_directive("这只是普通回答，没有工具") == []


def test_parse_directive_tolerates_bad_json():
    text = '<tool_call>not json</tool_call>'
    assert parse_directive(text) == []


def test_to_tool_schemas_has_required_fields():
    tools = [{"name": "foo", "description": "d",
              "parameters": {"type": "object", "properties": {"a": {"type": "string"}},
                             "required": ["a"]}}]
    schemas = to_tool_schemas(tools)
    assert schemas[0]["type"] == "function"
    assert schemas[0]["function"]["name"] == "foo"


def test_normalize_tool_calls_from_native():
    """模拟 OpenAI 原生 tool_calls 结构。"""
    native = [{"id": "call_1", "type": "function",
               "function": {"name": "get_node", "arguments": '{"node_id":"deepfm"}'}}]
    calls = normalize_tool_calls(native)
    assert calls[0].name == "get_node"
    assert calls[0].arguments == {"node_id": "deepfm"}


def test_normalize_tool_calls_bad_args_returns_empty():
    native = [{"id": "c", "type": "function", "function": {"name": "x", "arguments": "bad"}}]
    assert normalize_tool_calls(native) == []


# 追加到 tests/test_protocol.py
from agent.protocol import chat_with_tools, resolve_tool_calls


def test_chat_with_tools_sends_tools_field(monkeypatch):
    sent = {}

    def fake_urlopen(req, timeout=None):
        sent["body"] = json.loads(req.data.decode())
        class R:
            def read(self): return b'{"choices":[{"message":{"content":"","tool_calls":[]}}]}'
            def __enter__(self): return self
            def __exit__(self, *a): pass
        return R()
    monkeypatch.setattr("agent.protocol.urllib.request.urlopen", fake_urlopen)
    cfg = {"base_url": "http://x/v1", "api_key": "k", "model": "m"}
    tools = [{"name": "foo", "description": "d", "parameters": {"type": "object", "properties": {}}}]
    res = chat_with_tools(cfg, [{"role": "user", "content": "hi"}], tools)
    assert sent["body"]["tools"][0]["function"]["name"] == "foo"
    assert res["content"] == ""
    assert res["tool_calls"] == []


def test_resolve_tool_calls_prefers_native():
    native_msg = {"content": "", "tool_calls": [
        {"id": "c", "type": "function", "function": {"name": "get_progress", "arguments": "{}"}}]}
    calls = resolve_tool_calls(native_msg, chat_fn=None)
    assert len(calls) == 1
    assert calls[0].name == "get_progress"


def test_resolve_tool_calls_falls_back_to_directive():
    msg = {"content": '<tool_call>{"name":"get_node","arguments":{"node_id":"x"}}</tool_call>',
           "tool_calls": []}
    calls = resolve_tool_calls(msg, chat_fn=None)
    assert len(calls) == 1
    assert calls[0].name == "get_node"
