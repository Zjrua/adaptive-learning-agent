# tests/test_session.py
from __future__ import annotations
import time

from agent.session import SessionStore, Session


def test_get_or_create_returns_same_session():
    store = SessionStore(ttl=60)
    s1 = store.get_or_create("user-a")
    s2 = store.get_or_create("user-a")
    assert s1 is s2
    assert s1.uid == "user-a"
    assert s1.messages == []


def test_append_message_and_snapshot():
    store = SessionStore(ttl=60)
    s = store.get_or_create("user-a")
    s.messages.append({"role": "user", "content": "hi"})
    s2 = store.get_or_create("user-a")
    assert s2.messages == [{"role": "user", "content": "hi"}]


def test_expired_session_is_cleared():
    store = SessionStore(ttl=0)  # 立即过期
    s = store.get_or_create("user-a")
    s.messages.append({"role": "user", "content": "old"})
    time.sleep(0.01)
    s2 = store.get_or_create("user-a")
    assert s2.messages == []  # 过期后是全新 session
    assert s2 is not s


def test_clear():
    store = SessionStore(ttl=60)
    store.get_or_create("user-a")
    store.clear("user-a")
    assert "user-a" not in store._sessions


def test_snapshot_store_and_get():
    store = SessionStore(ttl=60)
    store.set_snapshot("u1", "graph", {"overview": {"overall_pct": 50}})
    snap = store.get_snapshot("u1", "graph")
    assert snap == {"overview": {"overall_pct": 50}}


def test_snapshot_miss_returns_none():
    store = SessionStore(ttl=60)
    assert store.get_snapshot("nope", "graph") is None
    assert store.get_snapshot("u1", "other_key") is None


def test_snapshot_invalidates_after_ttl():
    store = SessionStore(ttl=0)
    store.set_snapshot("u1", "graph", {"x": 1})
    time.sleep(0.01)
    assert store.get_snapshot("u1", "graph") is None


def test_snapshot_invalidate_manual():
    store = SessionStore(ttl=60)
    store.set_snapshot("u1", "graph", {"x": 1})
    store.invalidate_snapshot("u1", "graph")
    assert store.get_snapshot("u1", "graph") is None
