"""larkpub.py — 封装 lark-cli subprocess，发布飞书文档并返回 URL。"""
from __future__ import annotations
import re
import subprocess

URL_RE = re.compile(r"https?://\S+/docx/\S+")


def _run(cmd: list[str]) -> tuple[int, str, str]:
    """执行命令，返回 (returncode, stdout, stderr)。外部可被 monkeypatch。"""
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return p.returncode, p.stdout, p.stderr


def parse_doc_url(output: str) -> str:
    m = URL_RE.search(output)
    return m.group(0).strip() if m else ""


def publish_doc(xml_content: str, title: str = "学习笔记") -> str:
    """调 lark-cli docs +create 创建文档，返回飞书 URL。失败返回 ''。"""
    # 用 <title> 标签作为文档标题优先，否则用 title 参数
    cmd = ["lark-cli", "docs", "+create", "--as", "user",
           "--content", xml_content]
    try:
        code, out, err = _run(cmd)
    except Exception:
        return ""
    if code != 0:
        return ""
    return parse_doc_url(out)
