"""rag/store.py — JSONL 索引读写（零依赖标准库）。"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any


def read_chunks(path: Path) -> list[dict]:
    """读 JSONL，每行一个 chunk dict。文件不存在返回 []。"""
    if not path.exists():
        return []
    out: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def append_chunk(path: Path, chunk: dict) -> None:
    """追加一行（流式写，省内存）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(chunk, ensure_ascii=False) + "\n")


def write_meta(path: Path, meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def read_meta(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
