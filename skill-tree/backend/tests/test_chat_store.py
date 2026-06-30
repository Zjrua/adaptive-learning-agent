# tests/test_chat_store.py
from __future__ import annotations
import time
from pathlib import Path

from chat_store import ChatStore


def _new_store(tmp_path: Path) -> ChatStore:
    return ChatStore(tmp_path / "chat_history.json")


def test_new_store_has_empty_state(tmp_path: Path):
    s = _new_store(tmp_path)
    state = s.load()
    assert state["sessions"] == []
    assert state["current_session_id"] is None


def test_new_session_sets_current(tmp_path: Path):
    s = _new_store(tmp_path)
    sid = s.new_session()
    state = s.load()
    assert state["current_session_id"] == sid
    assert len(state["sessions"]) == 1
    assert state["sessions"][0]["id"] == sid
    assert state["sessions"][0]["messages"] == []
    assert state["sessions"][0]["title"] == "新会话"


def test_append_message_to_current(tmp_path: Path):
    s = _new_store(tmp_path)
    sid = s.new_session()
    s.append_message(sid, {"role": "user", "content": "你好", "ts": "2026-06-30T10:00:00"})
    msgs = s.load()["sessions"][0]["messages"]
    assert len(msgs) == 1
    assert msgs[0]["content"] == "你好"


def test_switch_current_session(tmp_path: Path):
    s = _new_store(tmp_path)
    s1 = s.new_session()
    s2 = s.new_session()
    assert s.load()["current_session_id"] == s2
    s.set_current(s1)
    assert s.load()["current_session_id"] == s1


def test_delete_session(tmp_path: Path):
    s = _new_store(tmp_path)
    s1 = s.new_session()
    s.delete_session(s1)
    assert s.load()["sessions"] == []


def test_set_title(tmp_path: Path):
    s = _new_store(tmp_path)
    sid = s.new_session()
    s.set_title(sid, "DeepFM 学习")
    assert s.load()["sessions"][0]["title"] == "DeepFM 学习"


def test_search_across_sessions(tmp_path: Path):
    s = _new_store(tmp_path)
    s1 = s.new_session()
    s.set_title(s1, "推荐学习")
    s.append_message(s1, {"role": "user", "content": "DeepFM 怎么实现", "ts": "x"})
    s.append_message(s1, {"role": "assistant", "content": "DeepFM 是华为提出", "ts": "x"})
    s2 = s.new_session()
    s.set_title(s2, "面试准备")
    s.append_message(s2, {"role": "user", "content": "DeepFM 面试题", "ts": "x"})

    hits = s.search("DeepFM")
    assert len(hits) == 3  # 3 条消息命中
    # 每条带 session_id/title/snippet
    assert all("session_id" in h and "snippet" in h and "session_title" in h for h in hits)
    assert any(h["session_title"] == "推荐学习" for h in hits)


def test_search_no_match(tmp_path: Path):
    s = _new_store(tmp_path)
    s1 = s.new_session()
    s.append_message(s1, {"role": "user", "content": "你好", "ts": "x"})
    assert s.search("不存在的内容") == []


def test_export_session_json(tmp_path: Path):
    s = _new_store(tmp_path)
    s1 = s.new_session()
    s.set_title(s1, "测试会话")
    s.append_message(s1, {"role": "user", "content": "hi", "ts": "x"})
    data = s.export(session_id=s1)
    assert data["title"] == "测试会话"
    assert len(data["messages"]) == 1
    assert data["messages"][0]["content"] == "hi"


def test_export_all_json(tmp_path: Path):
    s = _new_store(tmp_path)
    s.new_session()
    s.new_session()
    data = s.export(session_id=None)
    assert "sessions" in data
    assert len(data["sessions"]) == 2


def test_resolve_node_ref(tmp_path: Path):
    s = _new_store(tmp_path)
    # graph: 节点列表
    graph = {"nodes": [{"id": "deepfm", "name": "DeepFM", "category": "特征交叉",
                         "tasks": [{"title": "读论文"}], "depends_on": ["fm"]}]}
    refs = s.resolve_refs("#deepfm", graph=graph, dirs=[], resources=[])
    assert len(refs) == 1
    assert refs[0]["type"] == "node"
    assert "DeepFM" in refs[0]["content"]


def test_resolve_dir_ref(tmp_path: Path):
    s = _new_store(tmp_path)
    # dirs 带 nodes（新逻辑展开节点+进度）
    dirs = [{"id": "agent", "title": "AI Agent", "icon": "🤖", "color": "#a78bfa",
             "nodes": [
                 {"id": "transformer", "name": "Transformer", "state": "done", "pct": 100, "depends_on": []},
                 {"id": "react", "name": "ReAct 范式", "state": "locked", "pct": 0, "depends_on": ["transformer"]},
             ]}]
    refs = s.resolve_refs("$agent", graph={"nodes": []}, dirs=dirs, resources=[])
    assert len(refs) == 1
    assert refs[0]["type"] == "dir"
    content = refs[0]["content"]
    assert "AI Agent" in content
    assert "Transformer" in content           # 展开了节点
    assert "ReAct 范式" in content
    assert "可推进的下一步" in content         # react 前置 transformer done → 可推进
    assert "ReAct 范式" in content.split("可推进的下一步")[1]


def test_resolve_resource_ref(tmp_path: Path):
    s = _new_store(tmp_path)
    resources = [{"id": "dssm_paper", "label": "DSSM 论文", "url": "https://arxiv.org/abs/xxx"}]
    refs = s.resolve_refs("@dssm", graph={"nodes": []}, dirs=[], resources=resources)
    assert len(refs) == 1
    assert refs[0]["type"] == "resource"


def test_resolve_unknown_returns_empty(tmp_path: Path):
    s = _new_store(tmp_path)
    refs = s.resolve_refs("#不存在的节点", graph={"nodes": []}, dirs=[], resources=[])
    assert refs == []


def test_suggest_nodes_by_prefix(tmp_path: Path):
    s = _new_store(tmp_path)
    graph = {"nodes": [{"id": "deepfm", "name": "DeepFM"}, {"id": "dcn", "name": "DCN"}]}
    out = s.suggest("node", "deep", graph=graph, dirs=[], resources=[])
    assert len(out) == 1
    assert out[0]["id"] == "deepfm"
