# tests/test_indexer.py
from __future__ import annotations
import math

from rag.indexer import cosine


def test_cosine_identical():
    assert math.isclose(cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]), 1.0, abs_tol=1e-9)


def test_cosine_orthogonal():
    assert math.isclose(cosine([1.0, 0.0], [0.0, 1.0]), 0.0, abs_tol=1e-9)


def test_cosine_opposite():
    assert math.isclose(cosine([1.0, 0.0], [-1.0, 0.0]), -1.0, abs_tol=1e-9)


def test_cosine_zero_vector_safe():
    # 零向量不应抛异常，返回 0.0
    assert cosine([0.0, 0.0], [1.0, 2.0]) == 0.0


def test_cosine_dimension_mismatch_safe():
    # 维度不一致返回 0.0，不崩
    assert cosine([1.0], [1.0, 2.0]) == 0.0


from rag.indexer import chunk_source


def test_chunk_source_splits_by_toplevel_def_and_class():
    src = '''"""module doc."""\n\ndef foo(x):\n    """foo doc."""\n    return x\n\nclass Bar:\n    """bar doc."""\n    def method(self):\n        return 1\n'''
    chunks = chunk_source("pkg/mod.py", src)
    # 期望：1 个 module 头 + foo + Bar（method 不单独切，归到 Bar）
    symbols = [c["symbol"] for c in chunks]
    assert "foo" in symbols
    assert "Bar" in symbols
    # 每个 chunk 都带 file 与 text
    for c in chunks:
        assert c["file"] == "pkg/mod.py"
        assert c["text"].strip()
        assert c["id"].startswith("pkg/mod.py::")


def test_chunk_source_empty_file():
    assert chunk_source("empty.py", "") == []


def test_chunk_source_ids_unique():
    src = "def a():\n    pass\n\ndef b():\n    pass\n"
    chunks = chunk_source("m.py", src)
    ids = [c["id"] for c in chunks]
    assert len(ids) == len(set(ids))


from pathlib import Path
from rag.indexer import build_index


def test_build_index_embeds_and_skips_unchanged(tmp_path: Path, monkeypatch):
    # 造一个假项目
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    idx = tmp_path / "idx"

    # 桩 embed：返回每段文本字符长度的二维向量
    calls = {"n": 0}

    def fake_embed(cfg, texts):
        calls["n"] += len(texts)
        return [[float(len(t)), 1.0] for t in texts]

    monkeypatch.setattr("rag.indexer.embed", fake_embed)
    cfg = {"base_url": "x", "api_key": "y", "model": "m"}

    # 首次构建
    stats1 = build_index(cfg, proj, idx)
    assert stats1["chunks"] >= 1
    assert (idx / "code_chunks.jsonl").exists()
    assert calls["n"] >= 1

    # 第二次：文件未变，不应重新 embed
    calls["n"] = 0
    stats2 = build_index(cfg, proj, idx)
    assert calls["n"] == 0  # 增量：mtime 没变，跳过

    # 修改文件后，应重新 embed
    (proj / "a.py").write_text("def foo():\n    return 2\n", encoding="utf-8")
    calls["n"] = 0
    build_index(cfg, proj, idx)
    assert calls["n"] >= 1  # 重新索引了


# ─────────────── P1-#7: embedding 端点探测 ───────────────

def test_build_index_raises_when_embedding_unsupported(tmp_path: Path, monkeypatch):
    """供应商不支持 /embeddings 时，build_index 开头探测失败直接报错，不跑到一半才挂。"""
    from rag import indexer
    indexer._reset_embed_support_cache()
    # embed 抛错 → 探测判为不支持
    def failing_embed(cfg, texts):
        raise RuntimeError("404 not found")
    monkeypatch.setattr("rag.indexer.embed", failing_embed)

    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.py").write_text("def foo():\n    return 1\n", encoding="utf-8")
    cfg = {"base_url": "x", "api_key": "y", "model": "m"}

    import pytest
    with pytest.raises(ValueError, match="不支持 embedding"):
        build_index(cfg, proj, tmp_path / "idx")


def test_detect_embedding_support_caches_result(tmp_path: Path, monkeypatch):
    """探测结果按 base_url+model 缓存，只探一次。"""
    from rag import indexer
    indexer._reset_embed_support_cache()
    calls = {"n": 0}
    def fake_embed(cfg, texts):
        calls["n"] += 1
        return [[1.0, 2.0]]
    monkeypatch.setattr("rag.indexer.embed", fake_embed)
    cfg = {"base_url": "http://x/v1", "api_key": "y", "model": "m"}

    assert indexer.detect_embedding_support(cfg) is True
    assert indexer.detect_embedding_support(cfg) is True   # 缓存命中
    assert calls["n"] == 1   # 只探了一次
