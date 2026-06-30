"""agent/protocol.py — 工具调用混合协议。

两条路径归一化成 ToolCall：
- 原生 function calling：响应 message.tool_calls -> normalize_tool_calls
- 指令式回退：模型输出 <tool_call>{...}</tool_call> -> parse_directive
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class ToolCall:
    name: str
    arguments: dict = field(default_factory=dict)


_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)


def parse_directive(text: str) -> list[ToolCall]:
    """从指令式输出里提取所有 <tool_call>{...}</tool_call>。坏 JSON 跳过。"""
    out: list[ToolCall] = []
    for m in _TOOL_CALL_RE.finditer(text):
        try:
            obj = json.loads(m.group(1))
        except Exception:
            continue
        name = obj.get("name")
        args = obj.get("arguments") or obj.get("args") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}
        if name and isinstance(args, dict):
            out.append(ToolCall(name, args))
    return out


def normalize_tool_calls(native: list[dict] | None) -> list[ToolCall]:
    """把 OpenAI 原生 tool_calls 结构转成 ToolCall。坏 arguments 跳过。"""
    out: list[ToolCall] = []
    for tc in native or []:
        fn = tc.get("function") if isinstance(tc, dict) else None
        if not fn:
            continue
        name = fn.get("name")
        raw = fn.get("arguments", "{}")
        try:
            args = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except Exception:
            continue
        if name and isinstance(args, dict):
            out.append(ToolCall(name, args))
    return out


def to_tool_schemas(tools: list[dict]) -> list[dict]:
    """把内部工具定义转成 OpenAI tools 字段格式 [{type:function, function:{...}}]。"""
    out = []
    for t in tools:
        out.append({"type": "function", "function": {
            "name": t["name"], "description": t.get("description", ""),
            "parameters": t.get("parameters", {"type": "object", "properties": {}})}})
    return out
