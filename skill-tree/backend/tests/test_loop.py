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
    """Planner 判 chat → 单步直答，不进 ReAct。"""
    fake = FakeChat([
        {"content": '{"intent":"chat","sub_tasks":[],"needs_doc":false}', "tool_calls": []},
        {"content": "你好！加油学算法！", "tool_calls": []},
    ])
    ctx = _ctx()
    events = list(run_agent(ctx, "你好", chat_fn=fake, cfg={"base_url": "x", "api_key": "y"}))
    types = [e["type"] for e in events]
    full = "".join(e.get("content", "") for e in events if e["type"] == "delta")
    assert "thinking" in types
    assert "delta" in types and "final_done" in types
    assert "加油" in full
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
    assert any(e["type"] == "delta" for e in events)
    assert any(e["type"] == "final_done" for e in events)


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


def test_parse_react_action_with_chinese_comment():
    """Action 后跟中文括号注释,应只取工具名。"""
    step = parse_react("Thought: 查\nAction: get_progress（查进度）\nArguments: {}")
    assert step["type"] == "tool"
    assert step["action"] == "get_progress"


def test_parse_react_action_on_next_line():
    """Action 与工具名之间换行。"""
    step = parse_react("Thought: 查\nAction:\nget_progress\nArguments: {}")
    assert step["action"] == "get_progress"


def test_parse_react_multiline_json_arguments():
    """Arguments 是多行 JSON。"""
    text = ('Thought: x\nAction: add_node\nArguments: {\n  "description": "LightGCN"\n}')
    step = parse_react(text)
    assert step["type"] == "tool"
    assert step["arguments"] == {"description": "LightGCN"}


def test_parse_react_final_answer_multiline():
    """Final Answer 后是多行内容。"""
    step = parse_react("Thought: ok\nFinal Answer: 第一行\n第二行")
    assert step["type"] == "final"
    assert "第一行" in step["answer"] and "第二行" in step["answer"]


def test_loop_history_is_injected_into_messages():
    """前端发来的 history 应前置注入 Executor 的 messages。"""
    fake = FakeChat([
        {"content": '{"intent":"query","sub_tasks":[],"needs_doc":false}', "tool_calls": []},
        {"content": "Thought: 够\nFinal Answer: 你上次问的是 DCN。", "tool_calls": []},
    ])
    ctx = _ctx()
    history = [{"role": "user", "content": "DeepFM 学完了"},
               {"role": "assistant", "content": "建议学 DCN"}]
    list(run_agent(ctx, "那 DCN 之后呢", chat_fn=fake, cfg={"base_url": "x", "api_key": "y"},
                   history=history))
    # 第二次调用(Executor)的 messages 应含 history
    executor_call = fake.calls[1]
    roles_content = [(m["role"], m["content"]) for m in executor_call["messages"]]
    assert ("user", "DeepFM 学完了") in roles_content
    assert ("assistant", "建议学 DCN") in roles_content


def test_loop_chat_short_circuit_no_react():
    """chat intent → 单步直答,不进 ReAct(无 tool_call 事件)。"""
    fake = FakeChat([
        {"content": '{"intent":"chat","sub_tasks":[],"needs_doc":false}', "tool_calls": []},
        {"content": "你好！学算法能锻炼思维。", "tool_calls": []},
    ])
    ctx = _ctx()
    events = list(run_agent(ctx, "你好", chat_fn=fake, cfg={"base_url": "x", "api_key": "y"}))
    types = [e["type"] for e in events]
    assert "thinking" in types
    assert "delta" in types and "final_done" in types
    assert not any(e["type"] == "tool_call" for e in events)   # 无工具
    full = "".join(e["content"] for e in events if e["type"] == "delta")
    assert "学算法" in full
    # Executor (chat direct) called once; total calls = Planner(1) + chat direct(1) = 2
    assert len(fake.calls) == 2


def test_loop_reflect_ok_accepts_draft():
    """Reflect 判 ok=true → 直接接受草稿,不续跑。"""
    fake = FakeChat([
        {"content": '{"intent":"query","sub_tasks":[],"needs_doc":false}', "tool_calls": []},
        {"content": "Thought: x\nFinal Answer: 你整体 45%。", "tool_calls": []},
        {"content": '{"ok": true, "gap": ""}', "tool_calls": []},
    ])
    ctx = _ctx()
    events = list(run_agent(ctx, "进度", chat_fn=fake, cfg={"base_url": "x", "api_key": "y"}))
    full = "".join(e.get("content", "") for e in events if e["type"] == "delta")
    assert "45%" in full


def test_loop_reflect_gap_triggers_rerun():
    """Reflect 判 ok=false → 注入 gap 续跑一轮,再产出更完整答案。"""
    fake = FakeChat([
        {"content": '{"intent":"query","sub_tasks":[],"needs_doc":false}', "tool_calls": []},
        {"content": "Thought: x\nFinal Answer: 建议学 DCN。", "tool_calls": []},          # 草稿
        {"content": '{"ok": false, "gap": "没说为什么推荐 DCN"}', "tool_calls": []},        # Reflect → not ok
        {"content": "Thought: 补充\nFinal Answer: 建议 DCN，因为它承接 DeepFM 的特征交叉。", "tool_calls": []},  # 续跑草稿
        {"content": '{"ok": true, "gap": ""}', "tool_calls": []},                          # 二次 Reflect → ok
    ])
    ctx = _ctx()
    events = list(run_agent(ctx, "下一步学啥,为什么", chat_fn=fake,
                            cfg={"base_url": "x", "api_key": "y"}))
    full = "".join(e.get("content", "") for e in events if e["type"] == "delta")
    assert "特征交叉" in full    # 续跑后的内容被采纳


def test_loop_reflect_capped_accepts_second_draft():
    """Reflect 已用过一次 + 仍不 ok → 接受第二次草稿,不无限续跑。"""
    fake = FakeChat([
        {"content": '{"intent":"query","sub_tasks":[],"needs_doc":false}', "tool_calls": []},
        {"content": "Thought: x\nFinal Answer: 草稿A。", "tool_calls": []},
        {"content": '{"ok": false, "gap": "x"}', "tool_calls": []},
        {"content": "Thought: y\nFinal Answer: 草稿B。", "tool_calls": []},
        {"content": '{"ok": false, "gap": "y"}', "tool_calls": []},   # 二次仍不 ok,但 reflect 已用过
    ])
    ctx = _ctx()
    events = list(run_agent(ctx, "x", chat_fn=fake, cfg={"base_url": "x", "api_key": "y"}))
    assert any(e["type"] == "final_done" for e in events)   # 不卡死
    full = "".join(e.get("content", "") for e in events if e["type"] == "delta")
    assert "草稿B" in full    # 接受第二次草稿


def test_pick_doc_type_by_keyword():
    """含'复习/背/默写'→review,含'周报/本周/总结'→weekly,否则 note。"""
    from agent.loop import _pick_doc_type
    assert _pick_doc_type("帮我生成复习卡") == "review"
    assert _pick_doc_type("我要背一下 DeepFM 结构") == "review"
    assert _pick_doc_type("整理本周学习周报") == "weekly"
    assert _pick_doc_type("做个月度总结") == "weekly"
    assert _pick_doc_type("整理个 DeepFM 笔记") == "note"
    assert _pick_doc_type("讲讲 DCN") == "note"
