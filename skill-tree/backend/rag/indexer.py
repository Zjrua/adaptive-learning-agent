"""rag/indexer.py — 源码 AST chunking + embedding + 增量索引 + 余弦相似度。"""
from __future__ import annotations
import math
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
