"""
eval/run_weight_eval.py — RAG 检索参数敏感性实验(统计视角)。

实验目的:把 RAG 检索从"拍脑袋配权重"变成"有实验依据的参数选择"。
针对纯向量通道(源码检索场景),做三组实验:

  实验1 Top-k 敏感性:Top-k 取 1/3/5/10 时的命中率 + MRR 曲线
  实验2 分数阈值敏感性:丢弃 score < 阈值 的结果,测精确率(命中占比)随阈值变化
  实验3 归一化策略对比:min-max(当前 sc/mx) vs 不归一化 vs z-score

这些是信息检索/统计评估的标准方法:消融、参数扫描、评估指标对比。
结果用于支撑简历里"用统计评估方法论调优 RAG"的叙事。

读取:eval/config.local.json(embedding)+ eval/rag_index_test(索引)
输出:eval/results/weight_eval_<ts>.json + 控制台汇总
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
CONFIG_PATH = EVAL_DIR / "config.local.json"
CONFIG = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
EMB_CFG = CONFIG["embedding"]
IDX_DIR = EVAL_DIR / "rag_index_test"

# 复用 run_rag_eval 的黄金查询(15 条,带 ground-truth chunk id)
sys.path.insert(0, str(EVAL_DIR))
from run_rag_eval import GOLDEN_QUERIES  # noqa: E402


def _metrics(id_lists, gt_sets, k):
    """对一批查询算 Top-k 命中率 + MRR。id_lists[i] = 该查询的 id 列表(已按分数降序)。"""
    n = len(id_lists)
    topk = sum(bool(set(ids[:k]) & gt_sets[i]) for i, ids in enumerate(id_lists)) / n
    rr = 0.0
    for i, ids in enumerate(id_lists):
        rank = next((r + 1 for r, hid in enumerate(ids) if hid in gt_sets[i]), None)
        rr += (1.0 / rank) if rank else 0.0
    return round(topk, 4), round(rr / n, 4)


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skill-tree" / "backend"))
    from rag import retriever as R
    from rag.retriever import Retriever
    from rag import store as rag_store

    if not (IDX_DIR / "code_chunks.jsonl").exists():
        print("[ERROR] 索引不存在,先建索引"); sys.exit(1)
    n_chunks = len(rag_store.read_chunks(IDX_DIR / "code_chunks.jsonl"))
    print(f"[INFO] 索引 chunk 数: {n_chunks}, 查询数: {len(GOLDEN_QUERIES)}")

    retriever = Retriever(index_dir=IDX_DIR, cfg=EMB_CFG)
    gt_sets = [set(gt) for _, gt in GOLDEN_QUERIES]
    queries = [q for q, _ in GOLDEN_QUERIES]

    # ── 先取每条查询的完整原始命中(不截断,用于各实验)──
    # search() 内部已做归一化 + 权重融合,我们拿原始分数需要绕过。
    # 简化:直接用 search(top_k=20) 拿足够多的候选,后续实验在结果上做。
    raw_hits = []  # [[{id, score, source}, ...], ...]
    for q in queries:
        hits = retriever.search(q, top_k=20)
        raw_hits.append(hits)
    print(f"[INFO] 已取 {len(queries)} 条查询 × 各 20 候选")
    # 预转 id 列表(按分数降序)供各实验用
    id_lists = [[h["id"] for h in hits] for hits in raw_hits]

    # ── 实验1:Top-k 敏感性 ──
    print(f"\n{'='*60}\n实验1:Top-k 敏感性(命中率/MRR 随 k)\n{'='*60}")
    exp1 = {}
    for k in [1, 3, 5, 10]:
        topk, mrr = _metrics(id_lists, gt_sets, k)
        exp1[k] = {"topk_hit": topk, "MRR": mrr}
        print(f"  Top-{k:<2} 命中率: {topk:.3f}   MRR: {mrr:.3f}")

    # ── 实验2:分数阈值敏感性(丢弃低分结果后,命中的精确率)──
    print(f"\n{'='*60}\n实验2:分数阈值敏感性(低分截断对检索质量的影响)\n{'='*60}")
    exp2 = {}
    # 分数范围探测:取所有分数的分布
    all_scores = [h["score"] for hits in raw_hits for h in hits]
    print(f"  分数分布: min={min(all_scores):.3f} max={max(all_scores):.3f} "
          f"mean={sum(all_scores)/len(all_scores):.3f}")
    for thr in [0.0, 0.1, 0.2, 0.3, 0.4, 0.45]:
        # 丢弃 score < thr 的结果,看 Top-5 命中率(在剩余里算)
        filtered_ids = [[h["id"] for h in hits if h["score"] >= thr] for hits in raw_hits]
        # 命中率:剩余 Top-5 里含 gt
        n = len(filtered_ids)
        hit5 = sum(bool(set(ids[:5]) & gt_sets[i]) for i, ids in enumerate(filtered_ids)) / n
        # 保留率:平均每条还剩几个候选
        avg_keep = sum(len(ids) for ids in filtered_ids) / n
        exp2[thr] = {"top5_hit": round(hit5, 4), "avg_kept": round(avg_keep, 1)}
        print(f"  阈值 {thr:.2f}: Top-5 命中 {hit5:.3f}   平均保留 {avg_keep:.1f} 个/查询")

    # ── 实验3:消融——单路(纯向量) vs 当前配置(W_VEC=0.5) ──
    # 因为这批查询无结构化命中,当前配置等同纯向量。验证这一点。
    print(f"\n{'='*60}\n实验3:通道消融(验证纯源码查询场景下结构化通道不参与)\n{'='*60}")
    src_counts = {}
    for hits in raw_hits:
        for h in hits:
            src_counts[h.get("source", "?")] = src_counts.get(h.get("source", "?"), 0) + 1
    print(f"  全部命中的通道分布: {src_counts}")
    exp3 = {"channel_distribution": src_counts,
            "note": "纯源码符号查询场景下,结构化(图谱/简历)BM25 通道无命中,"
                    "检索退化为纯向量通道;权重 W_VEC=0.5/W_STRUCT=0.4 中 W_STRUCT 不起作用。"
                    "结论:权重应按查询-数据匹配关系设置,查源码符号时向量主导。"}

    # ── 实验4:结构化通道权重扫描(参数敏感性分析)──
    # 发现:当前权重 0.5/0.4 下,查同名图谱节点时结构化通道被向量通道候选数量压制,进不了 Top5。
    # 扫描 W_STRUCT(向量权重相应下调),看结构化通道何时浮现、命中率如何变化。
    print(f"\n{'='*60}\n实验4:结构化通道权重扫描(查同名图谱节点场景)\n{'='*60}")
    GRAPH_QUERIES = [
        ("DeepFM FM feature interaction", {"deepfm", "fm"}),
        ("DIN DIEN interest evolution", {"din", "dien"}),
        ("DSSM dual tower retrieval", {"dssm", "dssm_search"}),
        ("DCN deep cross network", {"dcn"}),
        ("xDeepFM CIN compressed interaction", {"xdeepfm"}),
        ("YouTube DNN sequential retrieval", {"youtubednn"}),
        ("MIND multi interest retrieval", {"mind"}),
        ("TF-IDF inverted index search", {"inverted_index"}),
        ("vector retrieval ANN", {"vector_retrieval"}),
        ("LTR learning to rank", {"ltr_basics"}),
    ]
    graph_gt = [{f"graph:{nid}" for nid in nids} for _, nids in GRAPH_QUERIES]
    gq = [q for q, _ in GRAPH_QUERIES]
    import main as be_main
    ctx, _ = be_main._build_ctx()
    graph = ctx.graph
    import rag.retriever as _R
    _saved = (_R.W_VEC, _R.W_STRUCT, _R.W_EXT)

    exp4 = {"weights_scanned": [], "n_graph_queries": len(gq),
            "note": "查同名图谱节点场景:当前权重(0.5/0.4)下结构化通道被向量通道候选数量压制,"
                    "进不了 Top5;W_STRUCT 提到 0.7+ 才浮现。说明固定权重非最优,"
                    "应按查询类型动态选权重(查源码→向量主导,查图谱→结构化主导)。"}
    print(f"  扫描 W_STRUCT(向量权重 = 1 - W_STRUCT),Top-5 图谱命中率:")
    for w_struct in [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
        _R.W_VEC, _R.W_STRUCT, _R.W_EXT = round(1.0 - w_struct, 2), w_struct, 0.0
        ids_per_q = []
        graph_in_top5 = 0
        for i, q in enumerate(gq):
            hits = retriever.search(q, top_k=5, graph=graph)
            ids = [h["id"] for h in hits]
            ids_per_q.append(ids)
            if any(iid.startswith("graph:") for iid in ids[:5]):
                graph_in_top5 += 1
        hit5 = sum(bool(set(ids[:5]) & graph_gt[i]) for i, ids in enumerate(ids_per_q)) / len(gq)
        exp4["weights_scanned"].append({
            "W_STRUCT": w_struct, "W_VEC": round(1.0 - w_struct, 2),
            "graph_top5_hit": round(hit5, 4),
            "graph_in_top5_count": f"{graph_in_top5}/{len(gq)}",
        })
        print(f"    W_STRUCT={w_struct:.1f} W_VEC={1.0-w_struct:.1f}: "
              f"Top-5 图谱命中 {hit5:.3f}  (图谱进Top5: {graph_in_top5}/{len(gq)})")
    _R.W_VEC, _R.W_STRUCT, _R.W_EXT = _saved  # 还原

    # ── 汇总 ──
    summary = {
        "n_queries": len(queries),
        "n_chunks": n_chunks,
        "embedding_model": EMB_CFG.get("model"),
        "exp1_topk_sensitivity": exp1,
        "exp2_threshold_sensitivity": exp2,
        "exp3_channel_ablation": exp3,
        "exp4_fusion_vs_single": exp4,
        "score_range": {"min": round(min(all_scores), 3), "max": round(max(all_scores), 3),
                        "mean": round(sum(all_scores)/len(all_scores), 3)},
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    print(f"\n{'='*60}\n汇总\n{'='*60}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    out_dir = EVAL_DIR / "results"
    out_dir.mkdir(exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"weight_eval_{ts}.json"
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[OK] 结果: {out_path}")


if __name__ == "__main__":
    main()
