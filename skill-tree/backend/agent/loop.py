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
    has_dir_ref = False   # 是否有 $方向 引用（需聚焦）
    if hasattr(ctx, "resolve_refs_fn") and ctx.resolve_refs_fn:
        refs = extract_refs(user_input)
        if refs:
            refs_str = " ".join(f"{s}{k}" for s, k in refs)
            has_dir_ref = any(s == "$" for s, _ in refs)
            try:
                resolved = ctx.resolve_refs_fn(refs_str)
                refs_text = "\n".join(r.get("content", "") for r in resolved)
            except Exception:
                refs_text = ""
    # 有 $方向 引用时，加聚焦指令，避免模型跑偏到其他方向
    if has_dir_ref:
        dir_names = ", ".join(k for s, k in extract_refs(user_input) if s == "$")
        refs_text = (refs_text + f"\n\n【重要】用户聚焦于「{dir_names}」方向，"
                     f"请只围绕该方向的节点和进度回答，不要扯到其他学习方向。"
                     f"若需查该方向详情，调用 get_direction 工具。")
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
    用全新的 system prompt（要求直接回答，不带 ReAct 格式），避免模型把
    Thought/Action/Final Answer 标记吐进流式输出。事实依据来自 Executor 收集的 Observation。
    回退：若 chat_fn 不支持流式，降级为一次性 delta + final_done。"""
    # 提取 Executor 收集的 Observation（工具产出）作为事实依据
    observations = [m["content"] for m in messages
                    if m.get("role") == "user" and "Observation:" in m.get("content", "")]
    # 用户原始问题（messages[1] 是首条 user）
    user_question = messages[1]["content"] if len(messages) > 1 else ""

    # 全新 system prompt：明确要求直接回答、不要 ReAct 格式
    sys_final = ("你是技能树系统的学习助手。现在请直接给用户最终回答。\n"
                 "要求：直接输出回答内容，不要写 Thought / Action / Final Answer 等标记，"
                 "不要解释你在做什么。用中文，可用 markdown（标题/列表/代码块/加粗）。")
    facts = "\n".join(observations) if observations else "（无额外检索信息，基于你的知识回答）"
    stream_messages = [
        {"role": "system", "content": sys_final},
        {"role": "user", "content": f"用户问题：{user_question}\n\n已知信息：\n{facts}\n\n请直接给出最终回答。"},
    ]
    try:
        chunks = chat_fn(cfg, stream_messages, tools=None, stream=True)
        # 前缀剥离状态机：模型可能仍带 "Final Answer:" / "Thought:" 等开头，逐 token 过滤
        prefix_buf = ""          # 累积开头字符，判断是否是 ReAct 前缀
        prefix_checked = False   # 是否已完成前缀判断
        for ev in chunks:
            if not (isinstance(ev, dict) and ev.get("type") == "delta"):
                continue
            piece = ev["content"]
            if not prefix_checked:
                prefix_buf += piece
                # 检测常见 ReAct 前缀
                stripped = _strip_react_prefix(prefix_buf)
                if stripped is not None:
                    # 已能判断：stripped 是去掉前缀后的剩余内容
                    prefix_checked = True
                    if stripped:
                        yield {"type": "delta", "content": stripped}
                    prefix_buf = ""
                elif len(prefix_buf) > 30:
                    # 超过 30 字仍未匹配前缀，认为无前缀，原样输出累积内容
                    prefix_checked = True
                    yield {"type": "delta", "content": prefix_buf}
                    prefix_buf = ""
                # 否则继续累积，不输出（等更多 token 判断）
            else:
                yield {"type": "delta", "content": piece}
        # 若全程没输出（前缀判断未结束且有残留），补发
        if not prefix_checked and prefix_buf:
            yield {"type": "delta", "content": _strip_react_prefix(prefix_buf) or prefix_buf}
        yield {"type": "final_done"}
        return
    except TypeError:
        pass  # chat_fn 不接受 stream 参数
    except Exception:
        pass
    # 降级：非流式一次性返回（同样剥离前缀）
    try:
        res = chat_fn(cfg, stream_messages, tools=None)
        yield {"type": "delta", "content": _strip_react_prefix(res.get("content", "")) or res.get("content", "")}
    except Exception as e:
        yield {"type": "delta", "content": f"（生成失败: {e}）"}
    yield {"type": "final_done"}


def _strip_react_prefix(text: str) -> "str | None":
    """剥离开头的 ReAct 前缀（Final Answer:/Thought:/Action: 等）。
    返回 None 表示尚无法判断（前缀可能未结束）；返回字符串表示已判断（可能为空）。"""
    for marker in ("Final Answer:", "Final answer:", "final answer:"):
        if text.startswith(marker):
            return text[len(marker):].lstrip()
    for marker in ("Thought:", "Action:", "Arguments:", "Observation:"):
        if text.startswith(marker):
            # 这些不该出现在最终回答里，整段视为前缀继续等待？不——直接剥离该行
            return text[len(marker):].lstrip()
    # 还没匹配任何前缀，但内容里已含换行或超过若干字符 → 无前缀
    if "\n" in text or len(text) > 20:
        return text
    return None  # 仍不确定，继续累积


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
