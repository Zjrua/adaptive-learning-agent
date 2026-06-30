# tests/test_larkpub.py
from __future__ import annotations

from larkpub import publish_doc, parse_doc_url


def test_parse_doc_url_from_stdout():
    out = "created: https://xxx.feishu.cn/docx/abc123XYZ"
    assert parse_doc_url(out) == "https://xxx.feishu.cn/docx/abc123XYZ"


def test_parse_doc_url_none():
    assert parse_doc_url("no url here") == ""


def test_publish_doc_calls_lark_cli(monkeypatch):
    captured = {}

    def fake_run(cmd):
        captured["cmd"] = cmd
        return 0, "created: https://xxx.feishu.cn/docx/abc123", ""

    monkeypatch.setattr("larkpub._run", fake_run)
    url = publish_doc("<title>T</title><p>hi</p>")
    assert url == "https://xxx.feishu.cn/docx/abc123"
    assert "lark-cli" in captured["cmd"][0]
    assert "+create" in captured["cmd"]
    assert "--as" in captured["cmd"]


def test_publish_doc_error_returns_empty(monkeypatch):
    monkeypatch.setattr("larkpub._run", lambda cmd: (1, "", "auth failed"))
    assert publish_doc("<p>x</p>") == ""
