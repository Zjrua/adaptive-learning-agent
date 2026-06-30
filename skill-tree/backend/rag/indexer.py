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
