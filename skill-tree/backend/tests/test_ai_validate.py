from __future__ import annotations
from ai import validate_node, slugify_id


def test_slugify_id_lowercases_and_replaces():
    assert slugify_id("DeepFM") == "deepfm"
    assert slugify_id("Light GCN!") == "light_gcn"
    assert slugify_id("xDeepFM") == "xdeepfm"


def test_validate_node_ok():
    node = {"id": "deepfm", "name": "DeepFM", "tasks": []}
    ok, errs = validate_node(node)
    assert ok and errs == []


def test_validate_node_missing_name():
    ok, errs = validate_node({"id": "x", "tasks": []})
    assert not ok and any("name" in e for e in errs)


def test_validate_node_missing_id():
    ok, errs = validate_node({"name": "DeepFM", "tasks": []})
    assert not ok and any("id" in e for e in errs)


def test_validate_node_tasks_must_be_list():
    ok, errs = validate_node({"id": "x", "name": "X", "tasks": "not list"})
    assert not ok
