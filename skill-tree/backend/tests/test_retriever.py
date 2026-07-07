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


# ─────────────── P1-#5: BM25 结构化通道 ───────────────

def test_bm25_multi_token_match_scores_higher(tmp_path: Path, monkeypatch):
    """多 token 命中的节点，BM25 分数应高于单 token 命中。"""
    monkeypatch.setattr("rag.retriever.embed", lambda cfg, texts: [[0.0, 0.0]])
    graph = {"nodes": [
        {"id": "deepfm", "name": "DeepFM", "category": "特征交叉",
         "tasks": [{"title": "DeepFM 特征交叉模型"}]},   # query "deepfm 特征" 双 token 命中
        {"id": "dssm", "name": "DSSM", "category": "双塔",
         "tasks": [{"title": "DSSM 检索模型"}]},          # 仅 "特征" 不命中
    ]}
    r = Retriever(index_dir=tmp_path, cfg={"base_url": "x", "api_key": "y", "model": "m"})
    hits = r.search("deepfm 特征", top_k=5, graph=graph, resume=None)
    graph_hits = [h for h in hits if h["source"] == "graph"]
    assert graph_hits
    assert graph_hits[0]["id"] == "graph:deepfm"   # 双 token 命中排前


def test_bm25_no_match_excluded(tmp_path: Path, monkeypatch):
    """完全不命中的节点不进入结构化通道结果。"""
    monkeypatch.setattr("rag.retriever.embed", lambda cfg, texts: [[0.0, 0.0]])
    graph = {"nodes": [{"id": "n1", "name": "DeepFM", "category": "特征交叉", "tasks": []}]}
    r = Retriever(index_dir=tmp_path, cfg={"base_url": "x", "api_key": "y", "model": "m"})
    hits = r.search("完全不相关的查询词", top_k=5, graph=graph, resume=None)
    assert not any(h["source"] == "graph" for h in hits)


# ─────────────── P1-#6: numpy 矩阵化向量检索 ───────────────

def test_vector_search_numpy_matrix_path(tmp_path: Path, monkeypatch):
    """numpy 可用时走矩阵化路径，结果与逐个 cosine 一致。"""
    try:
        import numpy as np  # noqa: F401
    except Exception:
        return   # 无 numpy 跳过

    chunks = tmp_path / "code_chunks.jsonl"
    _write_chunks(chunks, [
        {"id": "a::DeepFM", "file": "a.py", "symbol": "DeepFM",
         "text": "class DeepFM", "vector": [1.0, 0.0]},
        {"id": "a::DNN", "file": "a.py", "symbol": "DNN",
         "text": "class DNN", "vector": [0.0, 1.0]},
    ])
    monkeypatch.setattr("rag.retriever.embed", lambda cfg, texts: [[1.0, 0.0]])
    r = Retriever(index_dir=tmp_path, cfg={"base_url": "x", "api_key": "y", "model": "m"})
    hits = r.search("deepfm", top_k=2, graph=None, resume=None)
    assert hits[0]["id"] == "a::DeepFM"   # 与逐个 cosine 一致
    # 矩阵被加载
    assert r._matrix is not None


def test_vector_search_invalidate_clears_matrix(tmp_path: Path, monkeypatch):
    """invalidate() 后矩阵缓存清空，下次 search 重新加载。"""
    try:
        import numpy as np  # noqa: F401
    except Exception:
        return

    chunks = tmp_path / "code_chunks.jsonl"
    _write_chunks(chunks, [
        {"id": "a::DeepFM", "file": "a.py", "symbol": "DeepFM",
         "text": "class DeepFM", "vector": [1.0, 0.0]},
    ])
    monkeypatch.setattr("rag.retriever.embed", lambda cfg, texts: [[1.0, 0.0]])
    r = Retriever(index_dir=tmp_path, cfg={"base_url": "x", "api_key": "y", "model": "m"})
    r.search("deepfm", top_k=2, graph=None, resume=None)
    assert r._matrix is not None
    r.invalidate()
    assert r._matrix is None
    # 再次 search 会重新加载
    r.search("deepfm", top_k=2, graph=None, resume=None)
    assert r._matrix is not None
