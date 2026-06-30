"""chat_store.py — 多会话对话存储（JSON 文件，每用户独立）。

数据模型: {sessions: [Session], current_session_id: str|null}
Session: {id, title, created_at, updated_at, messages: [Msg]}
Msg: {role, content, ts, events?: [...]}
"""
from __future__ import annotations
import json
import time
from pathlib import Path


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class ChatStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> dict:
        if not self.path.exists():
            return {"sessions": [], "current_session_id": None, "updated_at": _now()}
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save(self, state: dict) -> None:
        state["updated_at"] = _now()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def new_session(self) -> str:
        state = self.load()
        sid = f"s_{int(time.time() * 1000)}"
        state["sessions"].append({
            "id": sid, "title": "新会话", "created_at": _now(),
            "updated_at": _now(), "messages": [],
        })
        state["current_session_id"] = sid
        self._save(state)
        return sid

    def append_message(self, session_id: str, msg: dict) -> None:
        state = self.load()
        for s in state["sessions"]:
            if s["id"] == session_id:
                s["messages"].append(msg)
                s["updated_at"] = _now()
                break
        self._save(state)

    def set_current(self, session_id: str) -> None:
        state = self.load()
        state["current_session_id"] = session_id
        self._save(state)

    def set_title(self, session_id: str, title: str) -> None:
        state = self.load()
        for s in state["sessions"]:
            if s["id"] == session_id:
                s["title"] = title
                break
        self._save(state)

    def delete_session(self, session_id: str) -> None:
        state = self.load()
        state["sessions"] = [s for s in state["sessions"] if s["id"] != session_id]
        if state["current_session_id"] == session_id:
            state["current_session_id"] = state["sessions"][0]["id"] if state["sessions"] else None
        self._save(state)

    def replace_all(self, sessions: list, current_session_id: str | None) -> None:
        """双写同步：前端发回完整数据，后端覆盖。"""
        self._save({"sessions": sessions, "current_session_id": current_session_id})
