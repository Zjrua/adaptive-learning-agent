"""agent/loop.py — Agent 主控：Planner → Executor(ReAct) → Writer。

run_agent 是生成器，yield SSE 事件 dict。上层（FastAPI）序列化成 text/event-stream。
注入点：chat_fn（可桩）、cfg、ctx；便于测试。
"""
from __future__ import annotations
import json
import re
from typing import Iterator

from agent.prompts import render_planner, render_executor
from agent.tools import TOOLS_EXECUTOR, tool_schema_text
from agent.tool_runtime import execute_tool, Context
from agent.protocol import resolve_tool_calls


_REF_RE = re.compile(r"([#@$])([^\s#@$，。、]+)")


def extract_refs(text: str) -> list[tuple[str, str]]:
    """提取文本里的 #/@/$ 引用，返回 [(symbol, key), ...]，去重保序。"""
    seen = set()
    out = []
    for m in _REF_RE.finditer(text):
        tag = (m.group(1), m.group(2))
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def inject_refs(system_prompt: str, refs_context: str) -> str:
    """把引用解析出的上下文注入 system prompt。无引用则原样返回。"""
    if not refs_context.strip():
        return system_prompt
    return system_prompt + "\n\n用户引用了以下内容（作为额外上下文）：\n" + refs_context


def parse_react(text: str) -> dict:
    """解析 ReAct 一步。返回 {type: tool|final, action?, arguments?, answer?}。
    - 含 Action 行 → tool 步（+ Arguments JSON，缺省 {}）
    - 含 Final Answer → final 步
    - 都没有 → 当作 final（answer = 原文，优雅降级）
    """
    if "Action:" in text:
        action = _after(text, "Action:").split()[0] if _after(text, "Action:").strip() else ""
        args_raw = _after(text, "Arguments:")
        try:
            args = json.loads(args_raw) if args_raw.strip() else {}
            if not isinstance(args, dict):
                args = {}
        except Exception:
            args = {}
        return {"type": "tool", "action": action, "arguments": args}
    if "Final Answer:" in text:
        return {"type": "final", "answer": _after(text, "Final Answer:")}
    return {"type": "final", "answer": text.strip()}


def _after(text: str, marker: str) -> str:
    i = text.find(marker)
    if i < 0:
        return ""
    return text[i + len(marker):].strip()


# 默认 chat_fn：真实工具调用协议
def _default_chat(cfg, messages, tools, stream=False):
    from agent.protocol import chat_with_tools, chat_stream
    if stream:
        # 流式：返回迭代器，逐 token yield {type:delta}
        return chat_stream(cfg, messages, tools)
    res = chat_with_tools(cfg, messages, tools)
    return res


def run_agent(ctx: Context, user_input: str, chat_fn=_default_chat,
              cfg: dict | None = None, max_steps: int = 6) -> Iterator[dict]:
    cfg = cfg or {}
    tools = TOOLS_EXECUTOR
    graph_summary = _graph_summary(ctx.graph)

    # ── 1. Planner 意图分流 ──
    sys_p = render_planner(progress_summary=graph_summary, user_input=user_input)
    try:
        pres = chat_fn(cfg, [{"role": "system", "content": sys_p},
                             {"role": "user", "content": user_input}], tools=None)
        intent = _safe_intent(pres.get("content", ""))
    except Exception:
        intent = {"intent": "query", "needs_doc": False}

    yield {"type": "thinking", "content": f"意图：{intent.get('intent', 'query')}"}

    # ── 2. Executor（chat 短路；其余走 ReAct）──
    sys_e = render_executor(tools_text=tool_schema_text(tools), graph_summary=graph_summary)
    # 引用预处理：解析用户消息里的 #/@/$ 并注入上下文
    refs_text = ""
    if hasattr(ctx, "resolve_refs_fn") and ctx.resolve_refs_fn:
        refs = extract_refs(user_input)
        if refs:
            refs_str = " ".join(f"{s}{k}" for s, k in refs)
            try:
                resolved = ctx.resolve_refs_fn(refs_str)
                refs_text = "\n".join(r.get("content", "") for r in resolved)
            except Exception:
                refs_text = ""
    sys_e = inject_refs(sys_e, refs_text)
    messages = [{"role": "system", "content": sys_e}, {"role": "user", "content": user_input}]

    for step_i in range(max_steps):
        try:
            res = chat_fn(cfg, messages, tools)
        except Exception as e:
            # 原生 tools 报错 → 回退到指令式
            try:
                res = chat_fn(cfg, messages, tools=None)
            except Exception as e2:
                yield {"type": "error", "content": f"模型调用失败: {e2}"}
                yield {"type": "done"}
                return

        # 同时尝试原生 tool_calls 与指令式
        calls = resolve_tool_calls(res, chat_fn)
        content = res.get("content", "")

        if not calls:
            # 走 ReAct 文本解析
            step = parse_react(content)
        else:
            # 原生工具调用：包装成 tool 步
            if len(calls) == 1:
                step = {"type": "tool", "action": calls[0].name, "arguments": calls[0].arguments}
            else:
                # 多工具：取第一个（保持 ReAct 单步语义）
                step = {"type": "tool", "action": calls[0].name, "arguments": calls[0].arguments}

        if step["type"] == "final":
            if step.get("answer") and not step["answer"].startswith("（已达到最大"):
                yield from _stream_final(ctx, messages, chat_fn, cfg)
            else:
                yield {"type": "final_answer", "content": step["answer"]}
            break

        # 工具步
        action = step["action"]
        args = step.get("arguments", {})
        yield {"type": "tool_call", "action": action, "arguments": args}
        try:
            observation = execute_tool(action, args, ctx)
        except Exception as e:
            observation = f"工具执行出错: {e}"
        yield {"type": "tool_result", "action": action, "content": observation}

        # 把这一轮塞回 messages 维持多轮
        messages.append({"role": "assistant", "content": content or f"Action: {action}"})
        messages.append({"role": "user", "content": f"Observation: {observation}"})

    else:
        # 达到最大步数仍未收敛 → 降级 final
        yield {"type": "final_answer", "content": "（已达到最大推理步数，基于已有信息停止。）"}

    # ── 3. Writer（条件触发）──
    if intent.get("needs_doc"):
        yield from _run_writer(ctx, user_input, messages, chat_fn, cfg)

    yield {"type": "done"}


def _stream_final(ctx, messages, chat_fn, cfg) -> "Iterator[dict]":
    """流式产出最终回答：用 chat_fn 的流式模式逐 token yield delta。
    回退：若 chat_fn 不支持流式，降级为一次性 delta + final_done。"""
    stream_messages = list(messages) + [
        {"role": "user", "content": "请基于以上思考和检索结果，给出最终回答（中文，可用 markdown）。"}]
    try:
        chunks = chat_fn(cfg, stream_messages, tools=None, stream=True)
        for ev in chunks:
            if isinstance(ev, dict) and ev.get("type") == "delta":
                yield {"type": "delta", "content": ev["content"]}
        yield {"type": "final_done"}
        return
    except TypeError:
        pass  # chat_fn 不接受 stream 参数
    except Exception:
        pass
    # 降级：非流式一次性返回
    try:
        res = chat_fn(cfg, stream_messages, tools=None)
        yield {"type": "delta", "content": res.get("content", "")}
    except Exception as e:
        yield {"type": "delta", "content": f"（生成失败: {e}）"}
    yield {"type": "final_done"}


def _run_writer(ctx, user_input, executor_messages, chat_fn, cfg) -> Iterator[dict]:
    from agent.prompts import render_writer
    materials = "\n".join(m.get("content", "") for m in executor_messages
                          if m.get("role") == "user" and "Observation" in m.get("content", ""))
    sys_w = render_writer(materials=materials[:2000], request=user_input)
    try:
        res = chat_fn(cfg, [{"role": "system", "content": sys_w},
                            {"role": "user", "content": "请生成文档。"}], tools=None)
        yield {"type": "doc_card", "doc_type": "note", "content": res.get("content", "")}
    except Exception as e:
        yield {"type": "error", "content": f"文档生成失败: {e}"}


def _safe_intent(text: str) -> dict:
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    return {"intent": "query", "needs_doc": False}


def _graph_summary(graph: dict) -> str:
    ov = graph.get("overview", {})
    nodes = graph.get("nodes", [])
    names = "、".join(n.get("name", n.get("id")) for n in nodes[:12])
    return (f"整体 {ov.get('overall_pct',0)}%"
            f"，已掌握 {ov.get('mastered_points',0)}/{ov.get('total_points',0)}。"
            f"节点：{names}")
