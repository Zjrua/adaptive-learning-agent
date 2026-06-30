"""测试桩：假 LLM 配置 + 假 chat 函数，避免真实网络调用。"""
from __future__ import annotations
from typing import Any, Iterator


def fake_cfg() -> dict:
    return {
        "provider": "test",
        "base_url": "http://localhost/v1",
        "api_key": "fake-key",
        "model": "fake-model",
        "json_mode": True,
    }


class FakeChat:
    """假 LLM：按预设队列返回响应。记录所有调用以便断言。

    responses: list[dict]，每个 dict 形如
        {"content": "...", "tool_calls": [ToolCall | dict, ...]}
    按顺序消费；耗尽后返回最后一个。
    """

    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.calls: list[dict] = []  # 记录每次调用的 messages/tools

    def __call__(self, cfg: dict, messages: list[dict], tools: list[dict] | None = None,
                 stream: bool = False) -> Any:
        self.calls.append({"messages": messages, "tools": tools, "stream": stream})
        if not self.responses:
            return {"content": "", "tool_calls": []}
        resp = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if stream:
            # 流式：把 content 拆成 delta 事件序列
            def gen() -> Iterator[dict]:
                for ch in resp.get("content", ""):
                    yield {"type": "delta", "content": ch}
                for tc in resp.get("tool_calls", []):
                    yield {"type": "tool_call", "tool_call": tc}
            return gen()
        return resp
