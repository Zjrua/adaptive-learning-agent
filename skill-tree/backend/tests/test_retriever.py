# tests/test_retriever.py
from __future__ import annotations
from pathlib import Path

from rag.retriever import Retriever


def _write_chunks(p: Path, items):
    import json
    with open(p, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


def test_search_vector_ranking(tmp_path: Path, monkeypatch):
    chunks = tmp_path / "code_chunks.jsonl"
    _write_chunks(chunks, [
        {"id": "a::DeepFM", "file": "a.py", "symbol": "DeepFM",
         "text": "class DeepFM: factorization machine", "vector": [1.0, 0.0]},
        {"id": "a::DNN", "file": "a.py", "symbol": "DNN",
         "text": "class DNN: deep neural net", "vector": [0.0, 1.0]},
    ])
    # 桩 embed：query "deepfm" → [1.0, 0.0]，与 DeepFM 最相似
    monkeypatch.setattr("rag.retriever.embed", lambda cfg, texts: [[1.0, 0.0]])
    r = Retriever(index_dir=tmp_path, cfg={"base_url": "x", "api_key": "y", "model": "m"})
    hits = r.search("deepfm", top_k=2, graph=None, resume=None)
    assert hits[0]["id"] == "a::DeepFM"
    assert "[1]" in hits[0]["ref"] or hits[0]["ref"].startswith("[")


def test_search_no_index_returns_empty(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("rag.retriever.embed", lambda cfg, texts: [[0.0, 0.0]])
    r = Retriever(index_dir=tmp_path, cfg={"base_url": "x", "api_key": "y", "model": "m"})
    assert r.search("anything", graph=None, resume=None) == []


def test_search_structural_match_with_graph(tmp_path: Path, monkeypatch):
    # 无向量索引，但有图谱：query 命中节点名 → 结构化召回
    monkeypatch.setattr("rag.retriever.embed", lambda cfg, texts: [[0.0, 0.0]])
    graph = {"nodes": [{"id": "deepfm", "name": "DeepFM", "category": "特征交叉",
                         "tasks": [{"title": "读 DeepFM 论文"}]}]}
    r = Retriever(index_dir=tmp_path, cfg={"base_url": "x", "api_key": "y", "model": "m"})
    hits = r.search("DeepFM", top_k=5, graph=graph, resume=None)
    assert any(h["source"] == "graph" for h in hits)


# 追加到 tests/test_retriever.py
def test_search_paper_external_channel(tmp_path: Path, monkeypatch):
    # query 含论文 id → 触发外部论文召回
    monkeypatch.setattr("rag.retriever.embed", lambda cfg, texts: [[0.0, 0.0]])
    cache = tmp_path / "paper_cache"
    monkeypatch.setattr("rag.paper_fetch.fetch_abstract",
                        lambda url, cd: {"id": "1703.04247", "abstract": "DeepFM paper", "url": url})
    r = Retriever(index_dir=tmp_path, cfg={"base_url": "x", "api_key": "y", "model": "m"})
    hits = r.search("1703.04247 DeepFM", top_k=5, graph=None, resume=None, paper_cache=cache)
    assert any(h["source"] == "paper" for h in hits)
