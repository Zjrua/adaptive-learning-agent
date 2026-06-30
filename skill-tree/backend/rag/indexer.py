"""rag/indexer.py — 源码 AST chunking + embedding + 增量索引 + 余弦相似度。"""
from __future__ import annotations
import math
from pathlib import Path
from typing import Any

try:
    import numpy as np  # 可选加速
    _HAS_NUMPY = True
except Exception:
    _HAS_NUMPY = False


def cosine(a: list[float], b: list[float]) -> float:
    """两向量余弦相似度。numpy 可用则用之，否则纯 math。零向量/维度不匹配返回 0.0。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    if _HAS_NUMPY:
        va, vb = np.asarray(a), np.asarray(b)
        na, nb = float(np.linalg.norm(va)), float(np.linalg.norm(vb))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return float(np.dot(va, vb) / (na * nb))
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


import ast


def chunk_source(file: str, source: str) -> list[dict]:
    """按 AST 把源码切成 chunk：每个顶层 def/class 一个，外加 module 头 docstring。
    嵌套 def 不单独切（归到所属 class）。返回 [{id, file, symbol, text}]（无 vector）。"""
    if not source.strip():
        return []
    chunks: list[dict] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # 解析失败的文件整体作为一个 chunk
        return [{"id": f"{file}::<raw>", "file": file, "symbol": "<raw>", "text": source[:2000]}]

    lines = source.splitlines()

    def text_of(node: ast.AST) -> str:
        seg = "\n".join(lines[node.lineno - 1: node.end_lineno])
        return seg

    # module 头 docstring（模块说明）作为独立 chunk
    if (isinstance(tree, ast.Module) and tree.body
            and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, ast.Constant)
            and isinstance(tree.body[0].value.value, str)):
        chunks.append({"id": f"{file}::<module>", "file": file,
                       "symbol": "<module>", "text": tree.body[0].value.value})

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            chunks.append({"id": f"{file}::{node.name}", "file": file,
                           "symbol": node.name, "text": text_of(node)})
    return chunks


import glob
import json
import os
import time
import urllib.request
import urllib.error

from rag import store


def embed(cfg: dict, texts: list[str]) -> list[list[float]]:
    """调 OpenAI 兼容 /embeddings，返回向量列表（与 texts 等长、同序）。"""
    if not texts:
        return []
    base = cfg["base_url"].rstrip("/")
    url = f"{base}/embeddings"
    body = json.dumps({"model": cfg.get("model") or "text-embedding-3-small",
                       "input": texts}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {cfg['api_key']}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    # OpenAI 格式：{data: [{embedding: [...]}, ...]} 按 index 排序
    items = sorted(data["data"], key=lambda d: d.get("index", 0))
    return [d["embedding"] for d in items]


def _file_mtime(path: Path) -> float:
    return os.path.getmtime(path)


def _file_mtime_safe(chunk: dict) -> float:
    return chunk.get("mtime", 0.0)


def build_index(cfg: dict, project_root: Path, index_dir: Path,
                batch_size: int = 32) -> dict:
    """扫描 project_root 下所有 .py，AST chunking + embedding，增量写 JSONL。
    返回 {chunks, files, built_at}。"""
    chunks_path = index_dir / "code_chunks.jsonl"
    meta_path = index_dir / "code_meta.json"
    # 读旧索引做 mtime 对比（增量）
    old_mtimes: dict[str, float] = {}
    for c in store.read_chunks(chunks_path):
        if c.get("mtime") and c.get("file"):
            old_mtimes[c["file"]] = max(old_mtimes.get(c["file"], 0.0), c["mtime"])

    # 收集所有 py 文件
    py_files = sorted(glob.glob(str(project_root / "**" / "*.py"), recursive=True))

    # 决定哪些需要（重新）索引
    pending: list[dict] = []  # 待 embed 的 chunk（无 vector）
    keep_files: set[str] = set()
    for fp in py_files:
        rel = os.path.relpath(fp, project_root).replace("\\", "/")
        mt = _file_mtime(Path(fp))
        keep_files.add(rel)
        if old_mtimes.get(rel, 0.0) >= mt:
            continue  # 未变，跳过
        try:
            src = open(fp, "r", encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for c in chunk_source(rel, src):
            c["mtime"] = mt
            pending.append(c)

    # 批量 embed
    if pending:
        for i in range(0, len(pending), batch_size):
            batch = pending[i:i + batch_size]
            vecs = embed(cfg, [c["text"] for c in batch])
            for c, v in zip(batch, vecs):
                c["vector"] = v

    # 重写索引：保留未变文件 + 新 chunk
    fresh: list[dict] = []
    for c in store.read_chunks(chunks_path):
        if c.get("file") in keep_files and old_mtimes.get(c["file"], 0.0) >= _file_mtime_safe(c):
            fresh.append(c)
    # 上面 _file_mtime_safe 用 chunk 自身 mtime
    fresh.extend(pending)

    # 重新写整文件（简单可靠；项目规模可接受）
    chunks_path.parent.mkdir(parents=True, exist_ok=True)
    with open(chunks_path, "w", encoding="utf-8") as f:
        for c in fresh:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")

    store.write_meta(meta_path, {
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": cfg.get("model", ""),
        "count": len(fresh),
        "project_root": str(project_root),
    })
    return {"chunks": len(fresh), "files": len(py_files),
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
