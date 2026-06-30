# tests/test_store.py
from __future__ import annotations
import json
from pathlib import Path

from rag.store import read_chunks, append_chunk, read_meta, write_meta


def test_append_and_read_chunks(tmp_path: Path):
    p = tmp_path / "code_chunks.jsonl"
    append_chunk(p, {"id": "c1", "file": "a.py", "symbol": "foo", "text": "def foo(): pass", "vector": [0.1, 0.2]})
    append_chunk(p, {"id": "c2", "file": "b.py", "symbol": "Bar", "text": "class Bar: ...", "vector": [0.3, 0.4]})
    chunks = read_chunks(p)
    assert len(chunks) == 2
    assert chunks[0]["id"] == "c1"
    assert chunks[1]["symbol"] == "Bar"


def test_read_chunks_missing_file_returns_empty(tmp_path: Path):
    assert read_chunks(tmp_path / "nope.jsonl") == []


def test_meta_roundtrip(tmp_path: Path):
    p = tmp_path / "code_meta.json"
    write_meta(p, {"built_at": "2026-06-30", "model": "emb-1", "dim": 2, "count": 5})
    meta = read_meta(p)
    assert meta["count"] == 5
    assert meta["model"] == "emb-1"


def test_read_meta_missing_returns_empty(tmp_path: Path):
    assert read_meta(tmp_path / "nope.json") == {}
