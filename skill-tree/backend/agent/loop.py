"""agent/loop.py — Agent 主控：Planner → Executor(ReAct) → Writer。

run_agent 是生成器，yield SSE 事件 dict。上层（FastAPI）序列化成 text/event-stream。
注入点：chat_fn（可桩）、cfg、ctx；便于测试。
"""
from __future__ import annotations
import json
import re
from typing import Iterator

from agent.prompts import render_planner, render_executor, render_chat_direct, render_reflect
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
    正则化容错:Action 后中文注释/括号、Action 换行、多行 JSON Arguments。
    都不匹配→当 final(原样 answer,优雅降级)。"""
    # 工具步:Action 行
    m_action = re.search(r"Action\s*:\s*([A-Za-z_]\w*)", text)
    if m_action:
        action = m_action.group(1)
        m_args = re.search(r"Arguments\s*:\s*([\s\S]*?)(?=\n(?:Thought|Action|Final Answer)\s*:|$)", text)
        args: dict = {}
        if m_args:
            raw = m_args.group(1).strip()
            if raw:
                try:
                    parsed = json.loads(raw)
                    args = parsed if isinstance(parsed, dict) else {}
                except Exception:
                    args = {}
        return {"type": "tool", "action": action, "arguments": args}
    # Final Answer
    m_final = re.search(r"Final Answer\s*:\s*([\s\S]*)", text)
    if m_final:
        return {"type": "final", "answer": m_final.group(1).strip()}
    # 都没有→当 final(原样)
    return {"type": "final", "answer": text.strip()}


# 默认 chat_fn：真实工具调用协议
def _default_chat(cfg, messages, tools, stream=False):
    from agent.protocol import chat_with_tools, chat_stream
    if stream:
        # 流式：返回迭代器，逐 token yield {type:delta}
        return chat_stream(cfg, messages, tools)
    res = chat_with_tools(cfg, messages, tools)
    return res


def run_agent(ctx: Context, user_input: str, chat_fn=_default_chat,
              cfg: dict | None = None, max_steps: int = 6,
              history: list[dict] | None = None) -> Iterator[dict]:
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

    # ── 2a. chat 短路:单步直答,不进 ReAct ──
    if intent.get("intent") == "chat":
        yield from _chat_direct(user_input, history or [], chat_fn, cfg)
        yield {"type": "done"}
        return

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
    messages = [{"role": "system", "content": sys_e}]
    for m in (history or []):
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_input})

    reflect_used = False   # Reflexion 仅允许 1 轮(query/produce)

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
            answer = step.get("answer", "")
            if not answer or answer.startswith("（已达到最大"):
                yield {"type": "final_answer", "content": answer}
                break
            # Reflexion(query/produce 才做,仅 1 轮)
            if intent.get("intent") in ("query", "produce") and not reflect_used:
                reflect_used = True   # 先置位:即使本轮续跑,下一轮 final 也不再 reflect(封顶 1 轮)
                ok, gap = _reflect(user_input, messages, answer, chat_fn, cfg)
                if not ok and (step_i + 1) < max_steps:
                    yield {"type": "thinking", "content": f"自查发现遗漏: {gap}，补充中…"}
                    messages.append({"role": "assistant", "content": answer})
                    messages.append({"role": "user",
                                     "content": f"上面的草稿遗漏: {gap}。请用工具补充后给出更完整的最终回答。"})
                    continue   # 续跑一轮(下一轮 final 时 reflect_used 已 True,不再 reflect)
            # 接受答案
            yield from _emit_text_as_delta(answer)
            yield {"type": "final_done"}
            break

        # 工具步
        action = step["action"]
        args = step.get("arguments", {})
        yield {"type": "tool_call", "action": action, "arguments": args}
        try:
            tresult = execute_tool(action, args, ctx)
            observation = tresult.get("text", "")
            for ev in tresult.get("events", []):
                yield ev
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


def _chat_direct(user_input, history, chat_fn, cfg) -> Iterator[dict]:
    """chat 意图:一次 LLM 直答,拿全文本后 chunk 成 delta(统一流式口径)。"""
    sys_c = render_chat_direct(_history_summary(history))
    messages = [{"role": "system", "content": sys_c}]
    for m in history:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_input})
    try:
        res = chat_fn(cfg, messages, tools=None)
        answer = res.get("content", "") or "（无回复）"
    except Exception as e:
        answer = f"（生成失败: {e}）"
    yield from _emit_text_as_delta(answer)
    yield {"type": "final_done"}


def _emit_text_as_delta(text: str, chunk_size: int = 8) -> Iterator[dict]:
    """把完整文本 chunk 成 delta 事件(统一流式口径:先拿全文本再分段吐)。"""
    for i in range(0, len(text), chunk_size):
        yield {"type": "delta", "content": text[i:i + chunk_size]}


def _reflect(user_input, messages, draft, chat_fn, cfg) -> tuple[bool, str]:
    """校验草稿是否回答了问题。返回 (ok, gap)。失败回退 ok=True(不阻塞主流程)。"""
    observations = "\n".join(m["content"].replace("Observation:", "").strip()
                             for m in messages
                             if m.get("role") == "user" and "Observation:" in m.get("content", ""))
    sys_r = render_reflect(question=user_input, observations=observations[:800], draft=draft[:800])
    try:
        res = chat_fn(cfg, [{"role": "system", "content": sys_r},
                            {"role": "user", "content": "请输出校验 JSON。"}], tools=None)
        obj = _safe_intent(res.get("content", ""))
        return bool(obj.get("ok", True)), str(obj.get("gap", ""))
    except Exception:
        return True, ""   # 回退:不阻塞


def _history_summary(history: list[dict]) -> str:
    if not history:
        return ""
    lines = []
    for m in history[-6:]:
        role = "用户" if m.get("role") == "user" else "助手"
        lines.append(f"{role}: {m.get('content','')[:80]}")
    return "\n".join(lines)


def _pick_doc_type(request: str) -> str:
    """按用户措辞判定文档类型。"""
    r = request
    if any(k in r for k in ("复习", "背", "默写", "review")):
        return "review"
    if any(k in r for k in ("周报", "本周", "总结", "weekly")):
        return "weekly"
    return "note"


def _run_writer(ctx, user_input, executor_messages, chat_fn, cfg) -> Iterator[dict]:
    from agent.prompts import render_writer
    doc_type = _pick_doc_type(user_input)
    materials = "\n".join(m.get("content", "") for m in executor_messages
                          if m.get("role") == "user" and "Observation" in m.get("content", ""))
    sys_w = render_writer(materials=materials[:2000], request=user_input, doc_type=doc_type)
    try:
        res = chat_fn(cfg, [{"role": "system", "content": sys_w},
                            {"role": "user", "content": f"请生成{doc_type}类型文档。"}], tools=None)
        content = res.get("content", "")
        # 标题:取首个 <title>...</title>,否则用类型默认名
        if "<title>" in content and "</title>" in content:
            title = content.split("</title>")[0].split("<title>")[-1]
        else:
            title = {"note": "学习笔记", "review": "复习卡", "weekly": "周报"}.get(doc_type, "文档")
        yield {"type": "doc_card", "doc_type": doc_type, "content": content, "title": title}
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
