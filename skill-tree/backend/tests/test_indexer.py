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
