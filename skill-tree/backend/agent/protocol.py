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


import urllib.request
import urllib.error


def chat_with_tools(cfg: dict, messages: list[dict], tools: list[dict] | None,
                    temperature: float = 0.5) -> dict:
    """带 tools 字段调 /chat/completions，返回 {content, tool_calls(原生结构)}。
    供应商不支持 tools 抛错时由上层捕获走回退。"""
    base = cfg["base_url"].rstrip("/")
    url = f"{base}/chat/completions"
    body: dict[str, Any] = {
        "model": cfg.get("model") or "gpt-3.5-turbo",
        "messages": messages,
        "temperature": temperature,
    }
    if tools:
        body["tools"] = to_tool_schemas(tools)
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {cfg['api_key']}")
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    msg = data["choices"][0]["message"]
    return {"content": msg.get("content") or "",
            "tool_calls": msg.get("tool_calls") or []}


def resolve_tool_calls(msg: dict, chat_fn) -> list[ToolCall]:
    """统一出口：优先原生 tool_calls，否则解析 content 里的指令式标记。"""
    native = normalize_tool_calls(msg.get("tool_calls") or [])
    if native:
        return native
    return parse_directive(msg.get("content") or "")


def chat_stream(cfg: dict, messages: list[dict], tools: list[dict] | None = None
                ) -> Iterator[dict]:
    """流式调 /chat/completions（stream:true），yield {type: delta|tool_call}。
    逐字吐 content delta，结束时吐 tool_call（若供应商流式也带工具）。"""
    base = cfg["base_url"].rstrip("/")
    url = f"{base}/chat/completions"
    body: dict[str, Any] = {"model": cfg.get("model") or "gpt-3.5-turbo",
                            "messages": messages, "temperature": 0.6, "stream": True}
    if tools:
        body["tools"] = to_tool_schemas(tools)
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {cfg['api_key']}")
    pending_tools: list[dict] = []
    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except Exception:
                continue
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            if delta.get("content"):
                yield {"type": "delta", "content": delta["content"]}
            if delta.get("tool_calls"):
                pending_tools.extend(delta["tool_calls"])
    for tc in normalize_tool_calls(pending_tools):
        yield {"type": "tool_call", "tool_call": tc}
