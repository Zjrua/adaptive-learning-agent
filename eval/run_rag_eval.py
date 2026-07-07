"""
eval/run_rag_eval.py — RAG 召回命中率实测。

前置:已用 embedding 配置建好索引(eval/rag_index_test 或 DATA_ROOT/rag_index)。
     建索引见 run_eval.py 注释或直接:
       cd skill-tree/backend
       python -c "from rag.indexer import build_index; ..." (见 eval/RESULTS.md)

测法:对每个查询,我知道它应该检索到的 chunk(symbol/file)。
      Top-k 命中率 = Top-k 结果里含 ground-truth chunk 的查询占比。
      MRR = 平均倒数排名(命中的排名倒数,未命中=0)。

读取配置:eval/config.local.json 的 embedding 段。
结果输出:eval/results/rag_eval_<timestamp>.json + 控制台汇总。
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
CONFIG_PATH = EVAL_DIR / "config.local.json"
if not CONFIG_PATH.exists():
    print("[ERROR] 找不到 eval/config.local.json。"); sys.exit(1)
CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
EMB_CFG = CONFIG["embedding"]

# 索引目录:优先用专门的测试索引,否则用 DATA_ROOT/rag_index
IDX_DIR = EVAL_DIR / "rag_index_test"
if not (IDX_DIR / "code_chunks.jsonl").exists():
    IDX_DIR = Path("DATA_ROOT_PLACEHOLDER")  # 后面用 main 的 rag_index_dir
    USE_MAIN = True
else:
    USE_MAIN = False


# ── 黄金查询:每条 = (查询, 期望命中的 chunk id 集合) ──
# chunk id 格式: "相对路径::symbol"。ground-truth 来自 DeepCTR-Torch 的模型定义。
# 一个查询可能有多个可接受答案(如 DeepFM 可命中 deepfm.py::DeepFM 或 ::<module>)。
def _gt(file: str, syms: list[str]) -> set[str]:
    return {f"{file}::{s}" for s in syms}

GOLDEN_QUERIES = [
    ("DeepFM 模型的结构", _gt("deepctr_torch/models/deepfm.py", ["DeepFM", "<module>"])),
    ("DeepFM 是什么", _gt("deepctr_torch/models/deepfm.py", ["DeepFM", "<module>"])),
    ("Deep & Cross Network DCN", _gt("deepctr_torch/models/dcn.py", ["DCN", "<module>"])),
    ("DCN deep cross network", _gt("deepctr_torch/models/dcn.py", ["DCN", "<module>"])),
    ("DIN deep interest network", _gt("deepctr_torch/models/din.py", ["DIN", "<module>"])),
    ("DIEN 序列兴趣演化", _gt("deepctr_torch/models/dien.py", ["DIEN", "<module>"])),
    ("xDeepFM compressed interaction", _gt("deepctr_torch/models/xdeepfm.py", ["xDeepFM", "<module>"])),
    ("PNN product based neural network", _gt("deepctr_torch/models/pnn.py", ["PNN", "<module>"])),
    ("AFM attentional factorization", _gt("deepctr_torch/models/afm.py", ["AFM", "<module>"])),
    ("AutoInt automatic feature interaction", _gt("deepctr_torch/models/autoint.py", ["AutoInt", "<module>"])),
    ("FiBiNET feature importance bilinear", _gt("deepctr_torch/models/fibinet.py", ["FiBiNET", "<module>"])),
    ("ESMM 多任务学习", _gt("deepctr_torch/models/multitask/esmm.py", ["ESMM", "<module>"])),
    ("MMoE 多门控专家", _gt("deepctr_torch/models/multitask/mmoe.py", ["MMOE", "<module>"])),
    ("PLE 渐进式多任务", _gt("deepctr_torch/models/multitask/ple.py", ["PLE", "<module>"])),
    ("特征交互 interaction layer", _gt("deepctr_torch/layers/interaction.py", ["<module>"])),
]


def main():
    import os
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skill-tree" / "backend"))
    from rag.retriever import Retriever

    if USE_MAIN:
        # 用 DATA_ROOT/rag_index(完整索引)
        os.environ.setdefault("DATA_ROOT", str(
            Path(__file__).resolve().parent.parent / "skill-tree" / "data"))
        import main as be_main
        idx_dir = be_main.rag_index_dir()
    else:
        idx_dir = IDX_DIR

    print(f"[INFO] 索引目录: {idx_dir}")
    if not (idx_dir / "code_chunks.jsonl").exists():
        print("[ERROR] 索引不存在,请先建索引。"); sys.exit(1)

    # chunk 总数(索引规模)
    from rag import store as rag_store
    n_chunks = len(rag_store.read_chunks(idx_dir / "code_chunks.jsonl"))
    print(f"[INFO] 索引 chunk 总数: {n_chunks}")

    retriever = Retriever(index_dir=idx_dir, cfg=EMB_CFG)

    results = []
    print(f"\n{'='*60}\nRAG 召回实测:共 {len(GOLDEN_QUERIES)} 条查询\n{'='*60}\n")
    for i, (q, gt_ids) in enumerate(GOLDEN_QUERIES, 1):
        hits = retriever.search(q, top_k=5)
        hit_ids = [h["id"] for h in hits]
        # Top-1/3/5 命中
        top1_hit = bool(set(hit_ids[:1]) & gt_ids)
        top3_hit = bool(set(hit_ids[:3]) & gt_ids)
        top5_hit = bool(set(hit_ids[:5]) & gt_ids)
        # 命中排名(用于 MRR)
        rank = next((r + 1 for r, hid in enumerate(hit_ids) if hid in gt_ids), None)
        rr = 1.0 / rank if rank else 0.0

        results.append({
            "q": q, "gt": sorted(gt_ids), "top5": hit_ids,
            "top1": top1_hit, "top3": top3_hit, "top5": top5_hit,
            "rank": rank, "rr": rr,
        })
        flag = "OK" if top5_hit else "MISS"
        print(f"[{i:2}/{len(GOLDEN_QUERIES)}] {q[:30]:<32} "
              f"Top1={int(top1_hit)} Top3={int(top3_hit)} Top5={int(top5_hit)} "
              f"rank={rank} [{flag}]")
        if not top5_hit:
            print(f"        期望: {sorted(gt_ids)[0]}")
            print(f"        实际 Top3: {hit_ids[:3]}")

    n = len(results)
    summary = {
        "n_queries": n,
        "index_chunks": n_chunks,
        "embedding_model": EMB_CFG.get("model"),
        "top1_hit_rate": round(sum(r["top1"] for r in results) / n, 4),
        "top3_hit_rate": round(sum(r["top3"] for r in results) / n, 4),
        "top5_hit_rate": round(sum(r["top5"] for r in results) / n, 4),
        "MRR": round(sum(r["rr"] for r in results) / n, 4),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    print(f"\n{'='*60}\nRAG 召回汇总 (model={summary['embedding_model']}, chunks={summary['index_chunks']})\n{'='*60}")
    for k, v in summary.items():
        if k in ("embedding_model", "timestamp"):
            continue
        print(f"  {k:.<24} {v}")

    out_dir = EVAL_DIR / "results"
    out_dir.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"rag_eval_{ts}.json"
    out_path.write_text(
        json.dumps({"summary": summary, "cases": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n[OK] 详细结果: {out_path}")


if __name__ == "__main__":
    main()
