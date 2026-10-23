"""
Benchmark / self-test for ``mia_emb.graph_retrieval`` (MGGR).

Runs fully on CPU with no model weights and no API keys:

  1. Self-test PPR against ``networkx.pagerank`` (correctness).
  2. Self-test Louvain on a two-clique bridge graph (must split into 2).
  3. End-to-end demo on the real legal corpus in ``data/legal_docs``:
     rule-based entity extraction -> co-occurrence KG -> mindscape-guided
     PPR -> Louvain communities -> hybrid rerank (TF-IDF stands in for the
     MiA-EMB vector channel).

Usage:
    python scripts/benchmark_retrieval.py
"""

import re
import sys
import time
from pathlib import Path

import numpy as np
import networkx as nx

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from mia_emb.graph_retrieval import (
    MindscapeGuidedDiffusion,
    LouvainDetector,
    HybridReranker,
    tokenize,
)

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    HAS_SKLEARN = True
except Exception:  # pragma: no cover
    HAS_SKLEARN = False


LAW_RE = re.compile(r"《[^》]{1,40}》")
CLAUSE_RE = re.compile(r"第[一二三四五六七八九十百千零〇0-9]+条")

BENCH_QUERY = "根据民法典，彩礼返还的条件是什么？"
BENCH_TERMS = ["彩礼", "婚姻", "家庭", "民法典", "返还"]


def load_documents(doc_dir: Path) -> list[str]:
    """Load a few .txt legal documents (auto encoding detection)."""
    docs: list[str] = []
    encodings = ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]
    for txt_file in sorted(doc_dir.glob("*.txt"))[:12]:
        for enc in encodings:
            try:
                content = txt_file.read_text(encoding=enc)
                if len(content.strip()) > 200:
                    docs.append(content)
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
    return docs


def extract_entities(doc: str, chunk_size: int = 600) -> list[set[str]]:
    """Rule-based entity extraction, returning one entity set per chunk.

    Entities are law names (``《...》``) and clause references (``第X条``),
    which is a cheap but domain-meaningful stand-in for the LLM-based
    extraction used in production.
    """
    chunks = [doc[i : i + chunk_size] for i in range(0, len(doc), chunk_size)]
    per_chunk: list[set[str]] = []
    for chunk in chunks:
        ents = set(LAW_RE.findall(chunk)) | set(CLAUSE_RE.findall(chunk))
        per_chunk.append(ents)
    return per_chunk


def build_graph(docs: list[str]) -> nx.Graph:
    """Co-occurrence KG: entities appearing in the same chunk share an edge."""
    g = nx.Graph()
    for doc in docs:
        for ent_set in extract_entities(doc):
            ents = sorted(ent_set)
            for e in ents:
                g.add_node(e)
            for i in range(len(ents)):
                for j in range(i + 1, len(ents)):
                    if g.has_edge(ents[i], ents[j]):
                        g[ents[i]][ents[j]]["weight"] += 1
                    else:
                        g.add_edge(ents[i], ents[j], weight=1)
    return g


def select_seeds(graph: nx.Graph, terms: list[str]) -> dict[str, float]:
    """Pick seed entities whose name contains a query term (mindscape-guided
    seeds would additionally weight the implicit-concept terms)."""
    seeds = {}
    for node in graph.nodes():
        for term in terms:
            if term in node:
                seeds[node] = seeds.get(node, 0.0) + 1.0
    return seeds


def one_hop_baseline(graph: nx.Graph, seeds: dict[str, float]) -> set[str]:
    """1-hop neighbour expansion (what ``_build_subgraph`` does today)."""
    reachable = set(seeds)
    for s in seeds:
        reachable.update(graph.neighbors(s))
    return reachable


def tfidf_vector_scores(graph: nx.Graph, query: str) -> dict[str, float]:
    """Stand-in for the MiA-EMB vector channel (TF-IDF cosine)."""
    nodes = list(graph.nodes())
    if not HAS_SKLEARN or not nodes:
        return {n: 0.0 for n in nodes}
    vec = TfidfVectorizer(analyzer=lambda t: tokenize(t, "zh"))
    try:
        X = vec.fit_transform([query] + nodes)
    except ValueError:
        return {n: 0.0 for n in nodes}
    sim = cosine_similarity(X[0:1], X[1:]).flatten()
    return {n: float(s) for n, s in zip(nodes, sim)}


def fmt_score(name: str, score: float) -> str:
    return f"  {name:8s} {score:.4f}"


def main() -> None:
    print("=" * 72)
    print("MGGR benchmark — mindscape-guided graph retrieval")
    print("=" * 72)

    # ---- 1. PPR self-test ------------------------------------------------
    print("\n[1] PPR self-test (vs networkx.pagerank)")
    g = nx.Graph()
    g.add_edges_from([(0, 1), (1, 2), (2, 3), (1, 3), (3, 4)])
    seeds = {0: 1.0, 4: 1.0}
    mine = MindscapeGuidedDiffusion().diffuse(g, seeds)
    ref = nx.pagerank(g, personalization=seeds, alpha=0.85)
    err = max(abs(mine[n] - ref[n]) for n in g.nodes())
    status = "PASS" if err < 1e-6 else "FAIL"
    print(f"  max |ours - networkx| = {err:.2e}  -> {status}")
    assert err < 1e-6, "PPR does not match networkx.pagerank"

    # ---- 2. Louvain self-test --------------------------------------------
    print("\n[2] Louvain self-test (two-clique bridge graph)")
    c = nx.Graph()
    c.add_edges_from([(0, 1), (1, 2), (0, 2)])  # clique A
    c.add_edges_from([(3, 4), (4, 5), (3, 5)])  # clique B
    c.add_edge(2, 3)  # bridge
    det = LouvainDetector()
    part = det.fit(c)
    n_comm = len(set(part.values()))
    q = det.modularity(c, part)
    print(f"  communities={n_comm}, modularity={q:.4f}")
    print(f"  partition={part}")
    ok = (n_comm == 2) and (q > 0.3)
    print(f"  -> {'PASS' if ok else 'FAIL'} (expect 2 communities, Q>0.3)")
    assert ok, "Louvain failed to split the two cliques"

    # ---- 3. Legal-corpus demo --------------------------------------------
    print("\n[3] Legal-corpus end-to-end demo")
    doc_dir = _PROJECT_ROOT / "data" / "legal_docs"
    if doc_dir.is_dir():
        docs = load_documents(doc_dir)
    else:  # pragma: no cover - fallback corpus
        docs = [
            "《中华人民共和国民法典》第一千零四十二条禁止包办、买卖婚姻，禁止借婚姻索取财物。最高人民法院关于审理涉彩礼纠纷案件适用法律若干问题的规定第三条明确了彩礼的认定标准。",
            "《中华人民共和国民法典》第一千零四十二条涉及婚姻家庭关系。最高人民法院关于适用民法典婚姻家庭编的解释规定了离婚财产分割规则。",
        ]
    print(f"  loaded {len(docs)} documents")

    t0 = time.perf_counter()
    graph = build_graph(docs)
    t_build = time.perf_counter() - t0
    print(f"  KG: {graph.number_of_nodes()} entities, {graph.number_of_edges()} edges ({t_build:.2f}s)")

    print(f"\n  query: {BENCH_QUERY}")
    seeds = select_seeds(graph, BENCH_TERMS)
    print(f"  seeds: {len(seeds)} entity(ies) matched")
    for s, w in list(seeds.items())[:5]:
        print(f"    - {s} (weight {w})")

    # PPR vs 1-hop baseline
    t0 = time.perf_counter()
    ppr = MindscapeGuidedDiffusion().diffuse(graph, seeds)
    t_ppr = time.perf_counter() - t0
    top_ppr = sorted(ppr, key=ppr.get, reverse=True)[:10]
    hop = one_hop_baseline(graph, seeds)
    print(f"\n  PPR diffusion ({t_ppr*1000:.1f}ms), top entities:")
    for n in top_ppr:
        print(fmt_score(n, ppr[n]))
    print(f"  1-hop baseline reaches {len(hop)} entities (PPR ranks a smooth superset)")

    # Louvain communities
    t0 = time.perf_counter()
    partition = LouvainDetector().fit(graph)
    t_louvain = time.perf_counter() - t0
    n_comm = len(set(partition.values()))
    q = LouvainDetector().modularity(graph, partition)
    print(f"\n  Louvain ({t_louvain*1000:.1f}ms): {n_comm} communities, modularity Q={q:.4f}")
    top_comm = partition.get(top_ppr[0]) if top_ppr else None
    members = [n for n, cc in partition.items() if cc == top_comm][:6]
    print(f"  community of top entity '{top_ppr[0] if top_ppr else ''}': {members}")

    # Hybrid rerank over the top PPR candidates
    vec_scores = tfidf_vector_scores(graph, BENCH_QUERY)
    candidates = [
        {"id": n, "name": n, "description": n, "vector_score": vec_scores.get(n, 0.0)}
        for n in top_ppr
    ]
    t0 = time.perf_counter()
    reranked = HybridReranker(graph).rerank(candidates, BENCH_QUERY, ppr_scores=ppr)
    t_rank = time.perf_counter() - t0
    print(f"\n  Hybrid rerank ({t_rank*1000:.1f}ms, 0 LLM calls) — top 5 fused:")
    for c in reranked[:5]:
        print(
            f"    fused={c['fused_score']:.4f} "
            f"(ppr={c['ppr_score']:.3f} bm25={c['bm25_score']:.3f} "
            f"cent={c['cent_score']:.3f} vec={c['vec_score']:.3f})  {c['name']}"
        )

    print("\n" + "=" * 72)
    print("All self-tests passed. Retrieval pipeline runs with zero model/LLM deps.")
    print("=" * 72)


if __name__ == "__main__":
    main()
