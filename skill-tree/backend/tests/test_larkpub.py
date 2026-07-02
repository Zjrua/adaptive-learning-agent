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
    url, _ = publish_doc("<title>T</title><p>hi</p>")
    assert url == "https://xxx.feishu.cn/docx/abc123"
    assert "lark-cli" in captured["cmd"][0]
    assert "+create" in captured["cmd"]
    assert "--as" in captured["cmd"]


def test_publish_doc_error_returns_empty(monkeypatch):
    monkeypatch.setattr("larkpub._run", lambda cmd: (1, "", "auth failed"))
    assert publish_doc("<p>x</p>") == ("", "")


def test_parse_doc_url_matches_wiki_and_docx():
    from larkpub import parse_doc_url
    assert parse_doc_url("see https://a.com/docx/abc123 done").startswith("https://a.com/docx/")
    assert parse_doc_url("see https://a.com/wiki/abc123 done").startswith("https://a.com/wiki/")


def test_publish_doc_with_wiki_space_two_step(monkeypatch):
    """wiki_space_id 有 → docs+create 拿 token,再 wiki+move,返回 wiki URL。"""
    import larkpub
    calls = []
    def fake_run(cmd):
        calls.append(cmd)
        s = " ".join(cmd)
        if "docs" in s and "+create" in s:
            return 0, "created https://a.com/docx/TOKEN123 done", ""
        if "wiki" in s and "+move" in s:
            return 0, "moved https://a.com/wiki/xyz done", ""
        return 1, "", "err"
    monkeypatch.setattr(larkpub, "_run", fake_run)
    url, kind = larkpub.publish_doc("<title>x</title>", "x", wiki_space_id="sp1")
    assert kind == "wiki"
    assert "/wiki/" in url
    assert any("docs" in " ".join(c) and "+create" in " ".join(c) for c in calls)
    assert any("wiki" in " ".join(c) and "+move" in " ".join(c) for c in calls)


def test_publish_doc_without_wiki_uses_docs_create(monkeypatch):
    """无 wiki_space_id → 仅 docs +create,返回 docx URL。"""
    import larkpub
    calls = []
    def fake_run(cmd):
        calls.append(cmd)
        return 0, "created https://a.com/docx/abc", ""
    monkeypatch.setattr(larkpub, "_run", fake_run)
    url, kind = larkpub.publish_doc("<title>x</title>", "x")
    assert kind == "docx"
    assert "/docx/" in url
    assert len(calls) == 1    # 只调了 docs+create,没 move


def test_publish_doc_wiki_move_fail_degrades_to_docx(monkeypatch):
    """wiki+move 失败 → 降级返回 docx(不抛错)。"""
    import larkpub
    def fake_run(cmd):
        s = " ".join(cmd)
        if "+create" in s:
            return 0, "created https://a.com/docx/TOKEN123", ""
        return 1, "", "move failed"
    monkeypatch.setattr(larkpub, "_run", fake_run)
    url, kind = larkpub.publish_doc("<title>x</title>", "x", wiki_space_id="sp1")
    assert kind == "docx"
    assert "/docx/" in url
