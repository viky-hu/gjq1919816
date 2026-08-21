"""
Mindscape-Guided Graph Retrieval (MGGR)
========================================

Model-agnostic, dependency-free upgrades for MiA-RAG's coarse (community)
retrieval channel.  These are drop-in replacements for the three weakest
parts of ``mia_emb/dual_channel.py``, and can be wired in later without
changing that file's public behaviour:

    dual_channel.py                     this module
    ----------------                    -----------
    ``_build_subgraph`` (1-hop)     ->  :class:`MindscapeGuidedDiffusion`
    ``_detect_communities``         ->  :class:`LouvainDetector`
    ``_rerank`` (LLM-based)         ->  :class:`HybridReranker`

Why this exists
---------------
The existing coarse channel expands a 1-hop neighbourhood around seed
entities, then runs community detection via the third-party ``community``
package (python-louvain).  On minimal installs ``community`` is absent, so
``_detect_communities`` silently degrades to "one community = whole graph".
This module (a) removes that dependency, (b) replaces the lossy 1-hop cut
with a smooth Personalized PageRank diffusion over the whole graph, and
(c) replaces the LLM-based reranker with a lexical + structural hybrid that
costs zero extra LLM calls.

Everything here is pure numpy / networkx -- no GPU, no model weights, no
external services -- so it runs and is testable on a CPU-only laptop.

Novel contribution (competition framing)
----------------------------------------
The new part is *mindscape-guided* diffusion: the PPR personalisation
vector is seeded not only by the query's explicit entity terms, but also by
the implicit-concept terms produced by query decomposition
(``DualChannelRetriever._parse_query``).  This turns "find neighbours" into
a principled relevance-propagation over the knowledge graph, then fuses the
graph score with a lexical (BM25) score and structural centrality so the
rerank step no longer depends on an LLM.

Math
----
Personalized PageRank (PPR) solves, for a transition matrix P (row
stochastic, ``P[u,v] = A[u,v] / deg_out(u)``) and seed distribution r0::

    r = (1 - alpha) r0 + alpha P^T r

which is the stationary distribution of a random walk that teleports back
to the seed distribution with probability ``1 - alpha``.  Closed form
``r = (1-alpha)(I - alpha P^T)^{-1} r0`` is solved by power iteration here.

Louvain (Blondel et al. 2008) greedily maximises modularity

    Q = sum_c [ Sigma_in(c)/m - gamma * (Sigma_tot(c)/(2m))^2 ]

via the local-moving phase; the gain of moving node i from community d to c
(no self-loops) is

    dQ = (k_i_in_c - k_i_in_d)/m - gamma * k_i (Sigma_tot(c) - Sigma_tot(d) + k_i)/(2m^2)
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any, Optional

import numpy as np
import networkx as nx

__all__ = [
    "tokenize",
    "BM25",
    "MindscapeGuidedDiffusion",
    "LouvainDetector",
    "HybridReranker",
]


# ---------------------------------------------------------------------------
# Lexical scoring (dependency-free BM25)
# ---------------------------------------------------------------------------

_HAN_RE = re.compile(r"[一-鿿]")
_ALNUM_RE = re.compile(r"[A-Za-z0-9]+")


def tokenize(text: str, lang: str = "zh") -> list[str]:
    """Tokenize text for lexical scoring.

    Chinese has no whitespace word boundaries, so we emit overlapping CJK
    bigrams plus latin/number runs; English uses whitespace + punctuation
    splitting.  Cheap and dependency-free -- adequate as a lexical baseline.
    """
    if not text:
        return []
    tokens: list[str] = []
    if lang == "zh":
        han = "".join(_HAN_RE.findall(text))
        tokens.extend("".join(han[i : i + 2]) for i in range(len(han) - 1))
        tokens.extend(_ALNUM_RE.findall(text))
    else:
        tokens = _ALNUM_RE.findall(text.lower())
    return tokens


class BM25:
    """Classic Okapi BM25, dependency-free.

    ``score(q, d) = sum_t IDF(t) * f(t,d) * (k1+1) / (f(t,d) + k1*(1-b+b*|d|/avgdl))``
    """

    def __init__(self, corpus: list[str], k1: float = 1.5, b: float = 0.75, lang: str = "zh"):
        self.k1 = k1
        self.b = b
        self.lang = lang
        self.docs = [tokenize(d, lang) for d in corpus]
        self.doc_len = [len(d) for d in self.docs]
        self.avgdl = float(np.mean(self.doc_len)) if self.doc_len else 0.0
        self.N = len(self.docs)
        self.df: Counter = Counter()
        for d in self.docs:
            for t in set(d):
                self.df[t] += 1

    def _idf(self, term: str) -> float:
        n = self.df.get(term, 0)
        return math.log(1.0 + (self.N - n + 0.5) / (n + 0.5))

    def score(self, query: str, doc_idx: int) -> float:
        q_terms = tokenize(query, self.lang)
        d = self.docs[doc_idx]
        tf = Counter(d)
        dl = self.doc_len[doc_idx] or 1
        total = 0.0
        for t in q_terms:
            f = tf.get(t, 0)
            if f == 0:
                continue
            denom = f + self.k1 * (1.0 - self.b + self.b * dl / self.avgdl)
            total += self._idf(t) * f * (self.k1 + 1.0) / denom
        return total


# ---------------------------------------------------------------------------
# Personalized PageRank diffusion
# ---------------------------------------------------------------------------

class MindscapeGuidedDiffusion:
    """Personalized PageRank (PPR) relevance diffusion over a knowledge graph.

    Parameters
    ----------
    alpha : teleport/damping factor in (0, 1).  Larger values spread the
        relevance further along edges; smaller values stay closer to seeds.
    tol, max_iter : power-iteration stopping criteria.
    """

    def __init__(self, alpha: float = 0.85, tol: float = 1e-8, max_iter: int = 300):
        self.alpha = alpha
        self.tol = tol
        self.max_iter = max_iter

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _edge_weight(d: dict) -> float:
        return float(d.get("weight", 1.0))

    def _transition_matrix(self, graph: nx.Graph) -> tuple[list[Any], dict[Any, int], np.ndarray]:
        nodes = list(graph.nodes())
        idx = {n: i for i, n in enumerate(nodes)}
        n = len(nodes)
        A = np.zeros((n, n), dtype=np.float64)
        directed = graph.is_directed()
        for u, v, d in graph.edges(data=True):
            w = self._edge_weight(d)
            iu, iv = idx[u], idx[v]
            A[iu, iv] += w
            if not directed:
                A[iv, iu] += w
        outdeg = A.sum(axis=1)
        P = np.zeros_like(A)
        nz = outdeg > 0
        P[nz, :] = A[nz, :] / outdeg[nz, None]
        return nodes, idx, P

    @staticmethod
    def _seed_vector(nodes: list[Any], idx: dict[Any, int], seeds: dict[Any, float]) -> np.ndarray:
        n = len(nodes)
        r0 = np.zeros(n, dtype=np.float64)
        total = 0.0
        for node, w in seeds.items():
            if node in idx:
                r0[idx[node]] += float(w)
                total += float(w)
        if total <= 0:
            r0[:] = 1.0 / n
        else:
            r0 /= total
        return r0

    # -- public API --------------------------------------------------------

    def diffuse(self, graph: nx.Graph, seeds: dict[Any, float], **kwargs) -> dict[Any, float]:
        """Return ``{node: ppr_score}`` for ``seeds`` = ``{node: weight}``.

        ``seeds`` is the "mindscape-guided" personalisation vector: pass
        explicit-entity terms *and* implicit-concept terms (both weighted) so
        diffusion is anchored to the full decomposed query, not just exact
        entity matches.
        """
        alpha = kwargs.get("alpha", self.alpha)
        tol = kwargs.get("tol", self.tol)
        max_iter = kwargs.get("max_iter", self.max_iter)
        nodes, idx, P = self._transition_matrix(graph)
        r0 = self._seed_vector(nodes, idx, seeds)
        r = r0.copy()
        for _ in range(max_iter):
            r_new = (1.0 - alpha) * r0 + alpha * (P.T @ r)
            diff = float(np.abs(r_new - r).sum())
            r = r_new
            if diff < tol:
                break
        return {nodes[i]: float(r[i]) for i in range(len(nodes))}


# ---------------------------------------------------------------------------
# Dependency-free Louvain community detection
# ---------------------------------------------------------------------------

class LouvainDetector:
    """Self-contained Louvain community detection (Blondel et al. 2008).

    Implements the local-moving phase with multiple passes over the graph,
    which captures the bulk of the modularity gain and is sufficient for the
    medium-sized knowledge graphs MiA-RAG builds.  The hierarchical
    aggregation phase is omitted for simplicity; a one-level pass is exact
    for the per-node gain formula below.

    Parameters
    ----------
    resolution : modularity resolution ``gamma`` (higher -> more, smaller
        communities; 1.0 is the default resolution).
    max_passes : bound on local-moving passes (safety only).
    """

    def __init__(self, resolution: float = 1.0, max_passes: int = 20):
        self.resolution = resolution
        self.max_passes = max_passes

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _edge_weight(d: dict) -> float:
        return float(d.get("weight", 1.0))

    def _total_weight(self, graph: nx.Graph) -> float:
        return sum(self._edge_weight(d) for _, _, d in graph.edges(data=True))

    def _weighted_degree(self, graph: nx.Graph, n) -> float:
        return sum(self._edge_weight(d) for _, d in graph[n].items())

    def _k_i_in(self, graph: nx.Graph, i, comm, partition: dict) -> float:
        s = 0.0
        for nb, d in graph[i].items():
            if partition.get(nb) == comm:
                s += self._edge_weight(d)
        return s

    def modularity(self, graph: nx.Graph, partition: dict) -> float:
        """Modularity of ``partition`` (``node -> community id``)."""
        m = self._total_weight(graph)
        if m <= 0:
            return 0.0
        members: dict[Any, list[Any]] = {}
        for n, c in partition.items():
            members.setdefault(c, []).append(n)
        deg = {n: self._weighted_degree(graph, n) for n in graph.nodes()}
        q = 0.0
        for c, mem in members.items():
            mset = set(mem)
            sin = sum(
                self._edge_weight(d)
                for u, v, d in graph.edges(data=True)
                if u in mset and v in mset
            )
            stot = sum(deg[n] for n in mem)
            q += (sin / m) - self.resolution * (stot / (2.0 * m)) ** 2
        return q

    # -- one level (local moving) ------------------------------------------

    def _one_level(self, graph: nx.Graph, partition: dict, node_order: list) -> float:
        m = self._total_weight(graph)
        if m <= 0:
            return 0.0
        deg = {n: self._weighted_degree(graph, n) for n in graph.nodes()}
        tot = defaultdict(float)
        for n, c in partition.items():
            tot[c] += deg[n]

        gain_total = 0.0
        changed = True
        passes = 0
        while changed and passes < self.max_passes:
            changed = False
            for i in node_order:
                d = partition[i]
                k_i = deg[i]
                k_i_in_d = self._k_i_in(graph, i, d, partition)
                neigh_comms = {partition[nb] for nb in graph[i] if nb in partition}
                best_c = d
                best_gain = 0.0
                for c in neigh_comms:
                    if c == d:
                        continue
                    k_i_in_c = self._k_i_in(graph, i, c, partition)
                    gain = (k_i_in_c - k_i_in_d) / m - self.resolution * k_i * (
                        tot[c] - tot[d] + k_i
                    ) / (2.0 * m * m)
                    if gain > best_gain:
                        best_gain = gain
                        best_c = c
                if best_c != d:
                    partition[i] = best_c
                    tot[d] -= k_i
                    tot[best_c] += k_i
                    gain_total += best_gain
                    changed = True
            passes += 1
        return gain_total

    # -- public API --------------------------------------------------------

    def fit(self, graph: nx.Graph) -> dict:
        """Detect communities, returning ``{node: community_id}``.

        Community ids are re-indexed to contiguous integers ``0..k-1`` sorted
        by community size (largest first) for stable, readable output.
        """
        if graph.number_of_nodes() == 0:
            return {}
        partition = {n: n for n in graph.nodes()}
        self._one_level(graph, partition, list(graph.nodes()))
        # re-index by descending community size
        sizes = Counter(partition.values())
        order = sorted(sizes, key=lambda c: sizes[c], reverse=True)
        reindex = {c: i for i, c in enumerate(order)}
        return {n: reindex[c] for n, c in partition.items()}


# ---------------------------------------------------------------------------
# Hybrid (graph + lexical + structural + vector) reranker
# ---------------------------------------------------------------------------

def _minmax(xs) -> list[float]:
    xs = np.asarray(xs, dtype=np.float64)
    if xs.size == 0:
        return []
    lo, hi = float(xs.min()), float(xs.max())
    if hi - lo < 1e-12:
        return [0.0] * int(xs.size)
    return (((xs - lo) / (hi - lo))).tolist()


class HybridReranker:
    """Fuse graph (PPR), lexical (BM25), structural (centrality) and vector
    similarity into a single relevance score, then re-rank candidates.

    ``fused(c) = w_ppr*p(c) + w_bm25*b(c) + w_cent*ct(c) + w_vec*v(c)``

    where each component is min-max normalised to ``[0, 1]``.  This replaces
    an LLM-based rerank with a model-free score, removing an LLM round-trip
    (latency + cost) from the retrieval path.
    """

    def __init__(self, graph: nx.Graph, weights: tuple[float, float, float, float] = (0.40, 0.20, 0.10, 0.30)):
        self.graph = graph
        self.weights = weights
        self._centrality: Optional[dict] = None

    def _centrality_scores(self) -> dict:
        if self._centrality is None:
            try:
                self._centrality = nx.degree_centrality(self.graph)
            except Exception:  # pragma: no cover - defensive
                self._centrality = {}
        return self._centrality

    def rerank(
        self,
        candidates: list[dict],
        query: str,
        ppr_scores: Optional[dict] = None,
        lang: str = "zh",
    ) -> list[dict]:
        """Re-rank ``candidates`` in place (and return the sorted list).

        Each candidate dict should carry: ``id`` (node id), ``name``,
        optional ``description`` and optional ``vector_score``.  The fused
        score and per-component scores are attached to each candidate, and the
        list is sorted by ``fused_score`` descending.
        """
        if not candidates:
            return candidates
        ppr_scores = ppr_scores or {}
        texts = [
            " ".join(filter(None, [c.get("name", ""), c.get("description", "")]))
            for c in candidates
        ]
        bm25 = BM25(texts, lang=lang)
        cent = self._centrality_scores()

        comps = {"ppr": [], "bm25": [], "cent": [], "vec": []}
        for i, c in enumerate(candidates):
            comps["ppr"].append(float(ppr_scores.get(c["id"], 0.0)))
            comps["bm25"].append(bm25.score(query, i))
            comps["cent"].append(float(cent.get(c["id"], 0.0)))
            comps["vec"].append(float(c.get("vector_score", 0.0)))

        for key in comps:
            comps[key] = _minmax(comps[key])

        w = self.weights
        for i, c in enumerate(candidates):
            c["fused_score"] = (
                w[0] * comps["ppr"][i]
                + w[1] * comps["bm25"][i]
                + w[2] * comps["cent"][i]
                + w[3] * comps["vec"][i]
            )
            c["ppr_score"] = comps["ppr"][i]
            c["bm25_score"] = comps["bm25"][i]
            c["cent_score"] = comps["cent"][i]
            c["vec_score"] = comps["vec"][i]

        candidates.sort(key=lambda x: x["fused_score"], reverse=True)
        return candidates
