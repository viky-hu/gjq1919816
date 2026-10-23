"""
Dual-Channel Retrieval: Fine (entity-level) + Coarse (community-level).

Implements Section 3.2 of the MiA-RAG design document:
  - Fine channel:   MiA-Emb entity-precise vector recall
  - Coarse channel: Graph traversal → Leiden community detection → summaries
  - Merge:          Structured prompt combining both channels
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .graph_retrieval import (
    HybridReranker,
    LouvainDetector,
    MindscapeGuidedDiffusion,
)

logger = logging.getLogger("dual_channel")


@dataclass
class FineChannelResult:
    entities: list[dict] = field(default_factory=list)
    chunks: list[dict] = field(default_factory=list)

    @property
    def entity_texts(self) -> list[str]:
        return [f"{e['name']}: {e['description']}" for e in self.entities[:15]]


@dataclass
class CoarseChannelResult:
    communities: list[dict] = field(default_factory=list)
    subgraph_summary: str = ""

    @property
    def community_texts(self) -> list[str]:
        return [
            f"主题{i+1}：{'、'.join(c['top_entities'][:5])}\n{c['summary']}"
            for i, c in enumerate(self.communities)
        ]


@dataclass
class QueryParseResult:
    """Result of LLM-based query decomposition (Section 3.2)."""
    original_query: str
    explicit_entities: str  # 具体法条、案例名、实体 → 向量通道
    implicit_concepts: str  # 抽象法律主题、上位概念 → 社区通道


@dataclass
class EvidenceItem:
    """Structured evidence for knowledge traceability (Section 6.4)."""
    source: str          # 来源：entity/chunk/community
    content: str         # 证据内容
    relevance: float = 0.0   # 相似度/置信度
    type: str = ""       # entity / chunk / community
    name: str = ""       # 实体名或片段ID


@dataclass
class DualChannelResult:
    query: str
    fine: FineChannelResult
    coarse: CoarseChannelResult
    answer: str = ""
    confidence: float = 0.0
    evidence: list[EvidenceItem] = field(default_factory=list)
    parsed_query: Optional[QueryParseResult] = None


class DualChannelRetriever:
    """Fine + Coarse dual-channel retrieval engine.

    Operates within a single node. The federated multi-node layer
    (Section 3.3) calls this locally on each node.
    """

    def __init__(self, rag):
        self.rag = rag
        self._last_ppr: dict = {}  # PPR scores cached from _build_subgraph for _rerank

    # ── Public API ─────────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        fine_top_k: int = 30,
        coarse_top_k: int = 15,
        community_max: int = 5,
    ) -> DualChannelResult:
        """Run fine + coarse channels and merge.

        Step 0: Parse query → explicit entities (向量通道) + implicit concepts (社区通道)
        Step 1: Fine channel uses explicit_entities for precision retrieval
        Step 2: Coarse channel uses implicit_concepts for community-level retrieval
        Step 3: Merge and generate answer
        """

        # Step 0: Query decomposition
        parsed = await self._parse_query(query)
        logger.info(
            f"Query parsed — entities: {parsed.explicit_entities[:60]}... | "
            f"concepts: {parsed.implicit_concepts[:60]}..."
        )

        # Steps 1+2: Parallel retrieval with decomposed queries
        fine_task = asyncio.create_task(
            self._fine_channel(parsed.explicit_entities, original_query=query, top_k=fine_top_k)
        )
        coarse_task = asyncio.create_task(
            self._coarse_channel(
                parsed.implicit_concepts,
                original_query=query,
                seed_top_k=coarse_top_k,
                community_max=community_max,
            )
        )

        fine = await fine_task
        coarse = await coarse_task

        # Step 2.5: Re-rank candidates by relevance
        fine, coarse = await self._rerank(query, fine, coarse)

        answer, confidence = await self._generate_answer(query, fine, coarse)

        # Build structured evidence for traceability
        evidence = self._build_evidence(fine, coarse)

        return DualChannelResult(
            query=query,
            fine=fine,
            coarse=coarse,
            answer=answer,
            confidence=confidence,
            evidence=evidence,
            parsed_query=parsed,
        )

    # ── Query Decomposition (Section 3.2) ─────────────────────────

    async def _parse_query(self, query: str) -> QueryParseResult:
        """Decompose query into explicit entities + implicit concepts.

        Per Section 3.2: the LLM decouples the query into two retrieval credentials:
          - 显式实体词 (explicit entities): concrete law articles, case names, entities
          - 隐式概念词 (implicit concepts): abstract legal themes, upper-level concepts
        """
        llm = self._get_llm_func()
        if llm is None:
            # Fallback: use full query for both channels
            return QueryParseResult(
                original_query=query,
                explicit_entities=query,
                implicit_concepts=query,
            )

        prompt = f"""请将以下查询拆解为两部分，用于不同的检索通道：

查询：{query}

严格按以下JSON格式输出（不要输出其他内容）：
{{"explicit_entities": "查询中出现的具体法条名称、案例名称、具体实体、专有名词，用逗号分隔", "implicit_concepts": "查询涉及的抽象法律主题、上位概念、法律领域分类，用逗号分隔"}}

示例：
查询：根据民法典第1042条，彩礼返还的条件是什么？
{{"explicit_entities": "民法典第1042条,彩礼", "implicit_concepts": "婚姻家庭法,财产纠纷,民事法律关系"}}"""

        try:
            raw = await llm(prompt)
            # Parse JSON from response
            match = re.search(r'\{[^{}]*"explicit_entities"[^{}]*"implicit_concepts"[^{}]*\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                return QueryParseResult(
                    original_query=query,
                    explicit_entities=data.get("explicit_entities", query),
                    implicit_concepts=data.get("implicit_concepts", query),
                )
        except Exception as e:
            logger.warning(f"Query parsing failed, using full query: {e}")

        return QueryParseResult(
            original_query=query,
            explicit_entities=query,
            implicit_concepts=query,
        )

    # ── Evidence Builder ─────────────────────────────────────────

    @staticmethod
    def _extract_source_label(content: str, chunk_id: str = "") -> str:
        """Extract a human-readable source label from chunk content."""
        import re
        # Try to find law/article references
        law_match = re.search(r'(《[^》]+》)', content)
        article_match = re.search(r'(第[一二三四五六七八九十百千零\d]+[条章节款])', content)
        if law_match and article_match:
            return f"{law_match.group(1)}{article_match.group(1)}"
        if law_match:
            return law_match.group(1)
        # Try to find a meaningful title from first sentence
        first_line = content.split("。")[0][:30].strip()
        if len(first_line) >= 4:
            return first_line
        # Fallback: use chunk type + index
        if chunk_id:
            return f"文献片段"
        return "知识片段"

    def _build_evidence(
        self, fine: FineChannelResult, coarse: CoarseChannelResult
    ) -> list[EvidenceItem]:
        """Build structured evidence list from both channels for traceability."""
        evidence = []

        try:
            # Fine channel: entities
            for e in fine.entities[:10]:
                evidence.append(EvidenceItem(
                    source=f"实体: {e.get('name', '')}",
                    content=e.get("description", "")[:500],
                    relevance=e.get("score", 0.0),
                    type="entity",
                    name=e.get("name", ""),
                ))

            # Fine channel: chunks - look up original file name
            for c in fine.chunks[:5]:
                content = c.get("content", "")
                chunk_id = c.get("id", "")
                # Try to find original file name from mapping
                try:
                    file_name = self.rag.lookup_file_name(content, chunk_id=chunk_id)
                except Exception:
                    file_name = ""
                if file_name:
                    label = file_name
                else:
                    label = self._extract_source_label(content, c.get("id", ""))
                evidence.append(EvidenceItem(
                    source=label,
                    content=content[:500],
                    relevance=c.get("score", 0.0),
                    type="chunk",
                    name=label,
                ))

            # Coarse channel: communities
            for i, comm in enumerate(coarse.communities[:5]):
                top_names = "、".join(comm.get("top_entities", [])[:5])
                evidence.append(EvidenceItem(
                    source=f"知识社区: {top_names}",
                    content=comm.get("summary", ""),
                    relevance=0.0,
                    type="community",
                    name=f"社区{i+1}({top_names})",
                ))
        except Exception as e:
            logger.warning(f"Error building evidence: {e}")

        return evidence

    # ── Fine Channel (3.2.1) ──────────────────────────────────────

    async def _fine_channel(
        self, entity_query: str, original_query: str = "", top_k: int = 30
    ) -> FineChannelResult:
        """Entity-level precision retrieval using MiA-Emb.

        Uses explicit entity terms for vector search (Section 3.2.1).
        Encodes with MiA-Emb + mindscape for global context fusion.
        """
        lr = self.rag.rag
        if lr is None:
            return FineChannelResult()

        # Encode original query with MiA-Emb + mindscape (preserves global context)
        q_embedding = self.rag.mia_embedding.encode_queries(
            [original_query or entity_query], mindscape=self.rag.mindscape, residual=True
        )

        # Vector search on entities using entity terms as query text
        query_vec = q_embedding[0].tolist()
        entity_results = await lr.entities_vdb.query(
            query=entity_query, top_k=top_k, query_embedding=query_vec
        )
        entities = []
        if entity_results:
            ids = [r["id"] for r in entity_results]
            scores = {r["id"]: r["distance"] for r in entity_results}
            entity_data = await lr.entity_chunks.get_by_ids(ids)
            for eid, edata in zip(ids, entity_data):
                if edata and isinstance(edata, dict):
                    entities.append({
                        "name": edata.get("entity_name", eid),
                        "type": edata.get("entity_type", ""),
                        "description": edata.get("description", ""),
                        "score": scores.get(eid, 0.0),
                    })

        # Also get top chunks using entity terms
        chunk_results = await lr.chunks_vdb.query(
            query=entity_query, top_k=10, query_embedding=query_vec
        )
        chunks = []
        if chunk_results:
            chunk_ids = [r["id"] for r in chunk_results]
            chunk_scores = {r["id"]: r["distance"] for r in chunk_results}
            chunk_data = await lr.text_chunks.get_by_ids(chunk_ids)
            for cid, cdata in zip(chunk_ids, chunk_data):
                if cdata and isinstance(cdata, dict):
                    content = cdata.get("content", cdata.get("tokens", ""))
                    if isinstance(content, list):
                        content = " ".join(str(t) for t in content)
                    chunks.append({
                        "id": cid,
                        "content": str(content)[:600],
                        "score": chunk_scores.get(cid, 0.0),
                    })

        return FineChannelResult(entities=entities, chunks=chunks)

    # ── Coarse Channel (3.2.2) ────────────────────────────────────

    async def _coarse_channel(
        self,
        concept_query: str,
        original_query: str = "",
        seed_top_k: int = 15,
        community_max: int = 5,
    ) -> CoarseChannelResult:
        """Graph-level community detection and summarization (Section 3.2.2).

        Uses implicit concepts for broad semantic search.
        1. Use concepts as keywords directly (already decomposed by _parse_query)
        2. Find seed entities via vector search
        3. Expand to neighbors (1-hop graph traversal)
        4. Build subgraph → Leiden community detection
        5. Generate summary per community
        """
        lr = self.rag.rag
        if lr is None:
            return CoarseChannelResult()

        # Step 1: Use implicit concepts as keywords directly
        keywords = concept_query
        if not keywords:
            return CoarseChannelResult()

        # Step 2: Find seed entities — encode original query for semantic coherence
        q_embedding = self.rag.mia_embedding.encode_queries(
            [original_query or concept_query], mindscape=self.rag.mindscape, residual=True
        )
        seed_entities = await self._find_seed_entities(q_embedding[0], keywords, seed_top_k)

        if not seed_entities:
            return CoarseChannelResult()

        # Step 3: Expand to neighbors and build subgraph
        subgraph = await self._build_subgraph(seed_entities)

        # Step 4: Leiden community detection
        communities = self._detect_communities(subgraph, community_max)

        # Step 5: Summarize each community (use original query for full context)
        full_query = original_query or concept_query
        communities = await self._summarize_communities(communities, full_query)

        # Generate overall subgraph summary
        subgraph_summary = await self._summarize_subgraph(communities, full_query)

        return CoarseChannelResult(
            communities=communities,
            subgraph_summary=subgraph_summary,
        )

    async def _find_seed_entities(
        self,
        query_embedding: np.ndarray,
        keywords: str,
        top_k: int,
    ) -> list[dict]:
        """Find seed entities via vector search, boosted by keyword match."""
        lr = self.rag.rag
        query_vec = query_embedding.tolist()
        results = await lr.entities_vdb.query(
            query=keywords, top_k=top_k * 2, query_embedding=query_vec
        )
        if not results:
            return []

        ids = [r["id"] for r in results]
        scores = {r["id"]: r["distance"] for r in results}
        entity_data = await lr.entity_chunks.get_by_ids(ids)

        kw_set = set(re.split(r"[、，,\s]+", keywords.lower()))
        seeds = []
        for eid, edata in zip(ids, entity_data):
            if not edata or not isinstance(edata, dict):
                continue
            name = str(edata.get("entity_name", "")).lower()
            desc = str(edata.get("description", "")).lower()
            combined = name + " " + desc

            # Boost: keyword overlap gives higher score
            boost = sum(1 for kw in kw_set if kw and kw in combined)
            score = scores.get(eid, 0.0) + boost * 0.05
            seeds.append({
                "id": eid,
                "name": edata.get("entity_name", eid),
                "type": edata.get("entity_type", ""),
                "description": edata.get("description", ""),
                "score": min(score, 1.0),
            })

        seeds.sort(key=lambda x: x["score"], reverse=True)
        return seeds[:top_k]

    async def _build_subgraph(self, seed_entities: list[dict], top_k: int = 50) -> dict:
        """Build a relevance-weighted local subgraph via mindscape-guided PPR.

        Replaces the old 1-hop expansion: seed entities anchor a Personalized
        PageRank diffusion over the full entity-relation graph, and the top
        ``top_k`` nodes by PPR score become the subgraph used for community
        detection.  Falls back to the original 1-hop expansion when the
        underlying storage is not a networkx graph.
        """
        lr = self.rag.rag
        graph = lr.chunk_entity_relation_graph

        # NetworkXStorage exposes its underlying networkx graph as ``._graph``.
        nx_graph = getattr(graph, "_graph", None)
        if nx_graph is None or nx_graph.number_of_nodes() == 0:
            return await self._build_subgraph_1hop(seed_entities)

        # Seed the diffusion with entity names (== graph node ids) weighted by
        # their fine-channel score.
        seeds = {
            s.get("name", s["id"]): float(s.get("score", 1.0))
            for s in seed_entities
        }
        ppr = MindscapeGuidedDiffusion().diffuse(nx_graph, seeds)
        self._last_ppr = ppr  # cache for the rerank stage

        ranked = sorted(ppr, key=ppr.get, reverse=True)
        keep = set(seeds) | set(ranked[:top_k])

        nodes = {n: {"id": n, "name": n} for n in keep}
        for s in seed_entities:
            name = s.get("name", s["id"])
            if name in nodes:
                nodes[name].update({
                    "name": name,
                    "type": s.get("type", ""),
                    "description": s.get("description", ""),
                })

        edges = [
            {"source": u, "target": v, "weight": d.get("weight", 1.0)}
            for u, v, d in nx_graph.edges(data=True)
            if u in keep and v in keep
        ]

        return {"nodes": nodes, "edges": edges}

    async def _build_subgraph_1hop(self, seed_entities: list[dict]) -> dict:
        """Original 1-hop neighbour expansion (fallback for non-networkx storage)."""
        lr = self.rag.rag
        graph = lr.chunk_entity_relation_graph
        seed_ids = {s["id"] for s in seed_entities}

        nodes = {}
        edges = []

        for seed in seed_entities[:10]:  # max 10 seeds for expansion
            sid = seed["id"]
            nodes[sid] = {
                "id": sid,
                "name": seed["name"],
                "type": seed["type"],
                "description": seed.get("description", ""),
            }

            try:
                neighbors = await graph.get_node_edges(sid)
                if neighbors is None:
                    continue

                if isinstance(neighbors, list):
                    for edge in neighbors:
                        # get_node_edges returns list[tuple[str, str]]: (src, tgt)
                        if isinstance(edge, (tuple, list)) and len(edge) >= 2:
                            src, tgt = str(edge[0]), str(edge[1])
                        elif isinstance(edge, dict):
                            src = edge.get("source", edge.get("src", ""))
                            tgt = edge.get("target", edge.get("tgt", ""))
                        else:
                            continue
                        edges.append({"source": src, "target": tgt})
                        if src not in nodes and src != sid:
                            nodes[src] = {"id": src, "name": src}
                        if tgt not in nodes and tgt != sid:
                            nodes[tgt] = {"id": tgt, "name": tgt}
            except Exception as e:
                logger.debug(f"Neighbor expansion for {sid}: {e}")

        return {"nodes": nodes, "edges": edges}

    def _detect_communities(self, subgraph: dict, max_communities: int = 5) -> list[dict]:
        """Leiden/Louvain community detection on subgraph."""
        nodes = subgraph.get("nodes", {})
        edges = subgraph.get("edges", [])

        if len(nodes) < 3:
            # Too small for communities — treat as single community
            return [{
                "id": 0,
                "entities": list(nodes.values()),
                "top_entities": [n.get("name", n["id"]) for n in list(nodes.values())[:5]],
            }]

        try:
            import networkx as nx
        except ImportError:
            # Fallback: trivial communities
            all_entities = list(nodes.values())
            return [{
                "id": 0,
                "entities": all_entities,
                "top_entities": [n.get("name", n["id"]) for n in all_entities[:5]],
            }]

        G = nx.Graph()
        for nid, ndata in nodes.items():
            G.add_node(nid, **ndata)
        for edge in edges:
            G.add_edge(edge["source"], edge["target"], weight=edge.get("weight", 1.0))

        if G.number_of_edges() == 0:
            all_entities = list(nodes.values())
            return [{
                "id": 0,
                "entities": all_entities,
                "top_entities": [n.get("name", n["id"]) for n in all_entities[:5]],
            }]

        partition = LouvainDetector().fit(G)

        # Group nodes by community
        comm_map: dict[int, list] = {}
        for nid, comm_id in partition.items():
            if comm_id not in comm_map:
                comm_map[comm_id] = []
            ndata = nodes.get(nid, {"id": nid, "name": nid})
            comm_map[comm_id].append(ndata)

        # Sort communities by size, keep top max_communities
        sorted_comms = sorted(comm_map.items(), key=lambda x: len(x[1]), reverse=True)
        communities = []
        for i, (comm_id, members) in enumerate(sorted_comms[:max_communities]):
            communities.append({
                "id": i,
                "entities": members,
                "top_entities": [m.get("name", m["id"]) for m in members[:5]],
            })

        return communities

    async def _summarize_communities(
        self,
        communities: list[dict],
        query: str,
    ) -> list[dict]:
        """Generate a one-line summary for each community."""
        llm = self._get_llm_func()
        if llm is None:
            for c in communities:
                c["summary"] = f"包含实体：{'、'.join(c['top_entities'])}"
            return communities

        for comm in communities:
            entity_list = "\n".join(
                f"- {e.get('name', e['id'])}: {e.get('description', '')[:120]}"
                for e in comm["entities"][:10]
            )
            prompt = f"""查询：{query}

以下是一个知识图谱社区中的实体列表：
{entity_list}

请用1句话概括这个社区覆盖的法律主题（15字以内，只输出概括）："""

            try:
                summary = await llm(prompt)
                comm["summary"] = summary.strip()
            except Exception:
                comm["summary"] = f"包含实体：{'、'.join(comm['top_entities'][:3])}"

        return communities

    async def _summarize_subgraph(
        self,
        communities: list[dict],
        query: str,
    ) -> str:
        """Generate a high-level summary of the entire subgraph."""
        if not communities:
            return ""

        llm = self._get_llm_func()
        if llm is None:
            return "；".join(c.get("summary", "") for c in communities)

        comm_text = "\n".join(
            f"社区{i+1}({c['summary']}): {', '.join(c['top_entities'][:3])}"
            for i, c in enumerate(communities)
        )
        prompt = f"""查询：{query}

检索到的知识图谱社区结构：
{comm_text}

请用2-3句话概述这些社区反映的全局法律知识框架（50字以内，只输出概述）："""

        try:
            return (await llm(prompt)).strip()
        except Exception:
            return "；".join(c.get("summary", "") for c in communities)

    # ── Re-ranking (Section 3.2.3) ─────────────────────────────────

    async def _rerank(
        self,
        query: str,
        fine: FineChannelResult,
        coarse: CoarseChannelResult,
        top_k: int = 10,
    ) -> tuple[FineChannelResult, CoarseChannelResult]:
        """Model-free re-ranking of fine + coarse candidates.

        Replaces the LLM-based rerank with a deterministic fused score over the
        fine-channel entities (PPR + BM25 + centrality).  Communities are left
        in their original order -- they are already summarised by relevance
        upstream.  Same ``top_k`` truncation contract as before, but with zero
        LLM round-trips.
        """
        if not fine.entities:
            return fine, coarse

        nx_graph = getattr(getattr(self.rag.rag, "chunk_entity_relation_graph", None), "_graph", None)
        if nx_graph is None:
            return fine, coarse  # no graph -> keep original order

        ppr = getattr(self, "_last_ppr", None) or {}

        # Graph nodes are keyed by entity name; PPR is keyed the same way.
        candidates = [
            {"id": e.get("name", ""), "name": e.get("name", ""), "description": e.get("description", "")}
            for e in fine.entities
        ]
        ppr_for = {c["id"]: ppr.get(c["id"], 0.0) for c in candidates}
        ranked = HybridReranker(nx_graph, weights=(0.5, 0.3, 0.2, 0.0)).rerank(
            candidates, query, ppr_scores=ppr_for
        )
        score_map = {c["id"]: c.get("fused_score", 0.0) for c in ranked}

        fine.entities.sort(key=lambda e: score_map.get(e.get("name", ""), 0.0), reverse=True)
        fine.entities = fine.entities[:top_k]
        logger.info(f"Re-ranked (model-free): {len(fine.entities)} entities")

        return fine, coarse

    # ── Merge (3.2.3) ─────────────────────────────────────────────

    async def _generate_answer(
        self,
        query: str,
        fine: FineChannelResult,
        coarse: CoarseChannelResult,
    ) -> tuple[str, float]:
        """Merge fine + coarse results, generate answer, compute confidence.

        Confidence uses formula (Section 3.3.2):
          C = α · sim(retrieved_entities, answer) + (1-α) · sim(answer, query)
        """
        prompt = self._build_merge_prompt(query, fine, coarse)

        llm = self._get_llm_func()
        if llm is None:
            return self._build_fallback_answer(fine, coarse), 0.5

        try:
            raw = await llm(prompt)
            answer, _ = self._parse_answer_confidence(raw)
            # Compute confidence via formula instead of LLM self-assessment
            confidence = await self._compute_confidence(query, answer, fine)
            return answer, confidence
        except Exception as e:
            logger.error(f"Answer generation failed: {e}")
            return self._build_fallback_answer(fine, coarse), 0.5

    async def _compute_confidence(
        self,
        query: str,
        answer: str,
        fine: FineChannelResult,
        alpha: float = 0.65,
    ) -> float:
        """Multi-dimensional confidence scoring (Section 3.3.2).

        C = α · sim(retrieved_entities, answer) + (1-α) · sim(answer, query)

        Uses MiA-Emb encoding + cosine similarity.
        """
        if not answer or not self.rag.mia_embedding:
            return 0.5

        try:
            # Encode query and answer
            embeddings = self.rag.mia_embedding.encode_documents([query, answer])
            q_emb = embeddings[0]
            a_emb = embeddings[1]

            # sim(answer, query)
            sim_aq = float(np.dot(q_emb, a_emb) / (np.linalg.norm(q_emb) * np.linalg.norm(a_emb) + 1e-8))

            # sim(retrieved_entities, answer)
            if fine.entities:
                entity_texts = [e.get("description", e.get("name", "")) for e in fine.entities[:10]]
                entity_texts = [t for t in entity_texts if t]
                if entity_texts:
                    e_embeddings = self.rag.mia_embedding.encode_documents(entity_texts)
                    # Average entity embedding
                    e_avg = np.mean(e_embeddings, axis=0)
                    sim_ea = float(np.dot(e_avg, a_emb) / (np.linalg.norm(e_avg) * np.linalg.norm(a_emb) + 1e-8))
                else:
                    sim_ea = sim_aq
            else:
                sim_ea = sim_aq

            # Weighted combination
            confidence = alpha * sim_ea + (1 - alpha) * sim_aq
            # Clamp to [0.1, 0.99]
            confidence = max(0.1, min(0.99, confidence))

            logger.info(f"Confidence: sim_ea={sim_ea:.4f}, sim_aq={sim_aq:.4f}, C={confidence:.4f}")
            return round(confidence, 4)

        except Exception as e:
            logger.warning(f"Confidence computation failed: {e}")
            return 0.5

    def _build_merge_prompt(self, query: str, fine: FineChannelResult, coarse: CoarseChannelResult) -> str:
        """Build structured merge prompt per Section 3.2.3."""
        parts = []

        # Fine channel results
        parts.append("【细通道-精确实体匹配】")
        if fine.entities:
            parts.append("\n".join(
                f"- {e['name']} [{e['type']}]: {e.get('description', '')[:200]}"
                for e in fine.entities[:15]
            ))
        else:
            parts.append("（无匹配实体）")

        # Coarse channel results
        parts.append("\n【粗通道-全局社区结构】")
        if coarse.subgraph_summary:
            parts.append(f"全局概述：{coarse.subgraph_summary}")
        for i, c in enumerate(coarse.communities):
            parts.append(
                f"社区{i+1}：{'、'.join(c['top_entities'][:5])}\n"
                f"  主题概括：{c.get('summary', '')}"
            )

        # Relevant chunks
        if fine.chunks:
            parts.append("\n【相关原文片段】")
            for i, chunk in enumerate(fine.chunks[:5]):
                parts.append(f"片段{i+1}：{chunk['content'][:300]}")

        # Instructions
        parts.append(f"""
---
【查询问题】
{query}

【回答要求】
1. 基于以上细通道（精确实体）和粗通道（全局框架）的信息，给出全面准确的回答
2. 引用的法条必须标注编号
3. 如果信息不足，请明确指出
4. 禁止使用markdown格式（不要用**加粗**、#标题、- 列表等符号），使用纯文本，用数字编号代替列表
5. 严格按以下JSON格式输出（不要输出其他内容）：
{{"answer": "你的回答"}}""")

        return "\n".join(parts)

    @staticmethod
    def _strip_markdown(text: str) -> str:
        """Remove markdown formatting symbols from answer text."""
        import re
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # **bold** → bold
        text = re.sub(r'\*(.+?)\*', r'\1', text)        # *italic* → italic
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)  # # heading → heading
        text = re.sub(r'^[-*+]\s+', '', text, flags=re.MULTILINE)  # - list item → list item
        text = re.sub(r'`(.+?)`', r'\1', text)          # `code` → code
        text = re.sub(r'~~(.+?)~~', r'\1', text)        # ~~strike~~ → strike
        return text.strip()

    def _parse_answer_confidence(self, raw: str) -> tuple[str, float]:
        """Parse JSON {answer} from LLM output. Confidence computed separately."""
        # Strategy 1: Find first '{' and parse from there
        try:
            start = raw.index('{')
            # Find matching '}' by counting braces
            depth = 0
            for i, ch in enumerate(raw[start:], start):
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        data = json.loads(raw[start:i+1])
                        return self._strip_markdown(data.get("answer", raw)), 0.0
        except (ValueError, json.JSONDecodeError):
            pass

        # Strategy 2: Try entire response as JSON
        try:
            data = json.loads(raw.strip())
            return self._strip_markdown(data.get("answer", raw)), 0.0
        except (json.JSONDecodeError, ValueError):
            return self._strip_markdown(raw), 0.0

    def _build_fallback_answer(self, fine: FineChannelResult, coarse: CoarseChannelResult) -> str:
        """Build a simple answer when LLM is unavailable."""
        parts = []
        if coarse.subgraph_summary:
            parts.append(coarse.subgraph_summary)
        if fine.entities:
            parts.append("相关实体：" + "、".join(e["name"] for e in fine.entities[:5]))
        for chunk in fine.chunks[:2]:
            parts.append(chunk["content"][:200])
        return "\n".join(parts) if parts else "无法生成回答（信息不足）"

    # ── Helpers ────────────────────────────────────────────────────

    def _get_llm_func(self):
        """Get LLM function from LightRAG instance."""
        if self.rag.rag and hasattr(self.rag.rag, 'llm_model_func'):
            return self.rag.rag.llm_model_func
        return None
