"""rag/retriever.py — 混合检索：精确(图谱/简历) + 向量(源码) + 外部(论文)，带排序融合。"""
from __future__ import annotations
import re
from pathlib import Path

from rag import store
from rag import paper_fetch
from rag.indexer import cosine, embed

W_STRUCT = 0.4
W_VEC = 0.5
W_EXT = 0.1


class Retriever:
    def __init__(self, index_dir, cfg: dict):
        self.index_dir = Path(index_dir)
        self.cfg = cfg

    def search(self, query: str, top_k: int = 5,
               graph: dict | None = None, resume: dict | None = None,
               paper_cache=None) -> list[dict]:
        """混合检索。返回 [{id, source, text, score, ref}]，按分数降序。"""
        results: list[dict] = []

        # 1) 向量通道（源码）
        chunks = store.read_chunks(self.index_dir / "code_chunks.jsonl")
        if chunks:
            qvec = embed(self.cfg, [query])[0] if query.strip() else None
            scored = []
            for c in chunks:
                v = c.get("vector")
                if v:
                    scored.append((cosine(qvec, v), c))
            scored.sort(key=lambda t: t[0], reverse=True)
            mx = scored[0][0] if scored and scored[0][0] > 0 else 1.0
            for sc, c in scored[:top_k]:
                if sc <= 0:
                    continue
                results.append({"id": c["id"], "source": "code", "file": c.get("file", ""),
                                "symbol": c.get("symbol", ""), "text": c.get("text", ""),
                                "score": W_VEC * (sc / mx if mx else 0.0)})

        # 2) 结构化通道（图谱）
        if graph:
            q = query.lower()
            mx = 1.0
            scored = []
            for n in graph.get("nodes", []):
                blob = (n.get("name", "") + " " + n.get("category", "") + " " +
                        " ".join(t.get("title", "") for t in n.get("tasks", []))).lower()
                if q and any(w in blob for w in _tokens(q)):
                    scored.append((1.0, n))
            for sc, n in scored[:top_k]:
                results.append({"id": "graph:" + n.get("id", ""), "source": "graph",
                                "text": f"[节点] {n.get('name')} ({n.get('category','')})",
                                "score": W_STRUCT})

        # 3) 简历通道（精确关键词）
        if resume:
            q = query.lower()
            for exp in resume.get("experience", []):
                blob = str(exp.get("desc", "")) + " " + str(exp.get("title", ""))
                if any(w in blob.lower() for w in _tokens(q)):
                    results.append({"id": "resume:" + str(exp.get("title", "")), "source": "resume",
                                    "text": f"[简历] {exp.get('title')}: {exp.get('desc','')}",
                                    "score": W_STRUCT})

        # 3.5) 外部通道（论文）：query 含 arxiv id 时抓 abstract
        if paper_cache is not None:
            aid = paper_fetch.extract_arxiv_id(query)
            if not aid:
                # 退路：匹配裸 arxiv id（如 "1703.04247"）
                m = re.search(r"\b(\d{4}\.\d{4,5})\b", query)
                aid = m.group(1) if m else None
            if aid:
                try:
                    rec = paper_fetch.fetch_abstract(f"https://arxiv.org/abs/{aid}", paper_cache)
                    if rec.get("abstract"):
                        results.append({"id": "paper:" + aid, "source": "paper",
                                        "text": f"[论文] {rec.get('title', aid)}: {rec['abstract'][:200]}",
                                        "score": W_EXT})
                except Exception:
                    pass

        # 去重（同 id 取高分）+ 归一化排序 + 加引用编号
        best: dict[str, dict] = {}
        for r in results:
            bid = r["id"]
            if bid not in best or r["score"] > best[bid]["score"]:
                best[bid] = r
        out = sorted(best.values(), key=lambda r: r["score"], reverse=True)[:top_k]
        for i, r in enumerate(out, 1):
            r["ref"] = f"[{i}]"
        return out


def _tokens(q: str) -> list[str]:
    """把查询切成关键词（中英混合）。"""
    return [w for w in re.split(r"[\s,，、。./]+", q.lower()) if len(w) >= 2]
