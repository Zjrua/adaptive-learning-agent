"""agent/session.py — 单用户会话内存管理（多轮历史 + 图谱快照 + TTL）。"""
from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Session:
    uid: str
    messages: list[dict] = field(default_factory=list)
    graph_snapshot: dict | None = None
    snapshots: dict = field(default_factory=dict)
    last_active: float = field(default_factory=time.time)


class SessionStore:
    def __init__(self, ttl: int = 1800):
        self.ttl = ttl
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, uid: str) -> Session:
        now = time.time()
        s = self._sessions.get(uid)
        if s is not None and (now - s.last_active) <= self.ttl:
            s.last_active = now
            return s
        # 过期或不存在 → 新建
        s = Session(uid=uid)
        self._sessions[uid] = s
        return s

    def clear(self, uid: str) -> None:
        self._sessions.pop(uid, None)

    def set_snapshot(self, uid: str, key: str, value: Any) -> None:
        s = self.get_or_create(uid)        # refreshes last_active
        s.snapshots[key] = value

    def get_snapshot(self, uid: str, key: str) -> Any | None:
        s = self._sessions.get(uid)
        if s is None or (time.time() - s.last_active) > self.ttl:
            return None
        return s.snapshots.get(key)

    def invalidate_snapshot(self, uid: str, key: str) -> None:
        s = self._sessions.get(uid)
        if s is not None:
            s.snapshots.pop(key, None)
