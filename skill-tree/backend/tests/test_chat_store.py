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
