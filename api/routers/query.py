"""
Query router: ask questions and retrieve history.
"""

import json
import logging
import os
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, status

logger = logging.getLogger("query")
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db, get_rag_manager, get_user_rag
from ..models import Node, QueryLog, User
from ..schemas import EvidenceItem, QueryHistoryResponse, QueryRequest, QueryResponse

router = APIRouter(prefix="/api/query", tags=["query"])

# Internal federation token for node-to-node communication
FEDERATION_INTERNAL_TOKEN = os.getenv("FEDERATION_INTERNAL_TOKEN", "")

# Compliance mode: when enabled, QueryLog does not store question/answer content
# per design doc 3.3.4 (audit logs should only store node/time/status/confidence)
AUDIT_COMPLIANCE_MODE = os.getenv("AUDIT_COMPLIANCE_MODE", "false").strip().lower() == "true"


def _extract_evidence(result: dict) -> list[EvidenceItem]:
    """Extract structured evidence from query result.

    Checks both the top-level "evidence" list (returned by query_global /
    _query_dual_channel) and the nested "context" dict (legacy fallback).
    """
    evidence: list[EvidenceItem] = []

    # Primary source: top-level evidence list from query_global
    for item in result.get("evidence", [])[:10]:
        if isinstance(item, dict) and item.get("content"):
            evidence.append(EvidenceItem(
                source=item.get("source", item.get("name", "unknown")),
                content=str(item.get("content", ""))[:500],
                relevance=float(item.get("relevance", item.get("score", 0.0))),
            ))

    # Fallback: extract from context dict when top-level evidence is empty
    if not evidence:
        ctx = result.get("context", {})
        if isinstance(ctx, dict):
            for chunk in ctx.get("fine_chunks", [])[:5]:
                if isinstance(chunk, dict) and chunk.get("content"):
                    evidence.append(EvidenceItem(
                        source=chunk.get("id", "unknown"),
                        content=chunk.get("content", "")[:500],
                        relevance=chunk.get("score", 0.0),
                    ))
            for comm in ctx.get("coarse_communities", [])[:3]:
                if isinstance(comm, dict):
                    evidence.append(EvidenceItem(
                        source=f"社区{comm.get('id', '?')}: {comm.get('summary', '')}",
                        content="、".join(comm.get("top_entities", [])[:5]),
                        relevance=0.7,
                    ))
            for chunk in ctx.get("chunks", [])[:3]:
                if isinstance(chunk, dict) and chunk.get("content"):
                    evidence.append(EvidenceItem(
                        source=chunk.get("source", "unknown"),
                        content=str(chunk.get("content", ""))[:500],
                        relevance=chunk.get("score", 0.0),
                    ))
    return evidence


@router.post("/", response_model=QueryResponse)
async def ask(
    body: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Force "mix" mode to activate dual-channel retrieval
    effective_mode = "mix" if body.mode in ("global", "hybrid") else body.mode
    rag = await get_user_rag(current_user.id)
    result = await rag.query(
        question=body.question,
        mode=effective_mode,
        top_k=body.top_k,
        chunk_top_k=body.chunk_top_k,
    )

    evidence = _extract_evidence(result)
    confidence = result.get("metadata", {}).get("confidence", None)
    evidence_json = json.dumps([e.model_dump() for e in evidence], ensure_ascii=False) if not AUDIT_COMPLIANCE_MODE else None

    log = QueryLog(
        user_id=current_user.id,
        question=body.question if not AUDIT_COMPLIANCE_MODE else None,
        answer=result["answer"] if not AUDIT_COMPLIANCE_MODE else None,
        confidence=confidence,
        mode=body.mode,
        mindscape_used=1 if result.get("metadata", {}).get("mindscape_used") else 0,
        evidence_json=evidence_json,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return QueryResponse(
        id=log.id,
        question=body.question,
        answer=result["answer"],
        confidence=confidence,
        mode=body.mode,
        mindscape_used=result.get("metadata", {}).get("mindscape_used", False),
        evidence=evidence,
        created_at=log.created_at,
    )


@router.get("/history", response_model=QueryHistoryResponse)
def history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    logs = (
        db.query(QueryLog)
        .filter(QueryLog.user_id == current_user.id)
        .order_by(QueryLog.created_at.desc())
        .limit(50)
        .all()
    )

    queries = []
    for log in logs:
        evidence = []
        if log.evidence_json:
            try:
                evidence = [EvidenceItem(**e) for e in json.loads(log.evidence_json)]
            except (json.JSONDecodeError, TypeError):
                pass

        queries.append(QueryResponse(
            id=log.id,
            question=log.question,
            answer=log.answer or "",
            confidence=log.confidence,
            mode=log.mode,
            mindscape_used=bool(log.mindscape_used),
            evidence=evidence,
            created_at=log.created_at,
        ))

    return QueryHistoryResponse(total=len(queries), queries=queries)


class InternalQueryRequest(BaseModel):
    """Simplified request for internal federation calls."""
    question: str = Field(..., min_length=1, max_length=4000)
    account: str = Field(default="", max_length=64)
    mode: str = Field(default="mix", pattern="^(local|global|hybrid|mix|naive)$")


class InternalQueryResponse(BaseModel):
    """Simplified response for internal federation calls."""
    requestId: str
    status: str
    answer: str
    confidence: float = 0.0
    mindscape_used: bool = False
    details: list[dict] = []
    evidence: list[dict] = []
    parsed_query: dict = {}


@router.post("/internal", response_model=InternalQueryResponse)
async def internal_query(
    body: InternalQueryRequest,
    x_federation_token: str = Header(None, alias="X-Federation-Token"),
    x_request_id: str = Header(None, alias="X-Request-Id"),
    db: Session = Depends(get_db),
):
    """
    Internal endpoint for federation node-to-node calls.
    Uses X-Federation-Token header for authentication instead of JWT.
    Returns rich evidence for knowledge traceability.
    """
    if not FEDERATION_INTERNAL_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Federation internal token not configured",
        )
    if not x_federation_token or not secrets.compare_digest(x_federation_token, FEDERATION_INTERNAL_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid federation token",
        )

    manager = get_rag_manager()

    # Ensure the querying user's RAG instance exists
    if body.account:
        user = db.query(User).filter(User.username == body.account).first()
        if user:
            try:
                await manager.get_user_rag(user.id)
            except Exception as e:
                logger.warning(f"Failed to init RAG for user {user.id}: {e}")

    # Force "mix" mode to activate dual-channel retrieval (MiA-Emb + community detection)
    # LightRAG native "global" mode is fragile and often returns empty results
    effective_mode = "mix" if body.mode in ("global", "hybrid") else body.mode
    logger.info(f"[InternalQuery] mode={body.mode}->{effective_mode}, account={body.account}")
    if effective_mode == "local" and body.account:
        user_for_query = db.query(User).filter(User.username == body.account).first()
        if user_for_query:
            user_rag = await manager.get_user_rag(user_for_query.id)
            result = await user_rag.query(
                question=body.question,
                mode=effective_mode,
                top_k=60,
                chunk_top_k=20,
            )
        else:
            result = await manager.query_global(
                question=body.question,
                mode=effective_mode,
                top_k=60,
                chunk_top_k=20,
            )
    else:
        result = await manager.query_global(
            question=body.question,
            mode=effective_mode,
            top_k=60,
            chunk_top_k=20,
        )

    # Log query for statistics (same as /api/query/ endpoint)
    if body.account:
        user = db.query(User).filter(User.username == body.account).first()
        if user:
            confidence = result.get("metadata", {}).get("confidence", None)
            log = QueryLog(
                user_id=user.id,
                question=body.question if not AUDIT_COMPLIANCE_MODE else None,
                answer=result.get("answer", "")[:500] if not AUDIT_COMPLIANCE_MODE else None,
                confidence=confidence,
                mode=body.mode,
                mindscape_used=1 if result.get("metadata", {}).get("mindscape_used") else 0,
            )
            db.add(log)
            db.commit()

    # Convert evidence to frontend-expected format
    # Primary: use top-level evidence from query_global
    details = []
    for item in result.get("evidence", [])[:5]:
        if isinstance(item, dict) and item.get("content"):
            details.append({
                "source": item.get("source", item.get("name", "unknown")),
                "content": str(item.get("content", ""))[:500],
                "score": float(item.get("relevance", item.get("score", 0.0))),
            })
    # Fallback: extract from context if top-level evidence is empty
    if not details:
        ctx = result.get("context", {})
        if isinstance(ctx, dict):
            for chunk in ctx.get("fine_chunks", [])[:5]:
                if isinstance(chunk, dict) and chunk.get("content"):
                    details.append({
                        "source": chunk.get("id", "unknown"),
                        "content": chunk.get("content", "")[:500],
                        "score": chunk.get("score", 0.0),
                    })

    # Build evidence list for traceability
    evidence_list = []
    for e in _extract_evidence(result):
        evidence_list.append({
            "source": e.source,
            "content": e.content,
            "relevance": e.relevance,
        })

    metadata = result.get("metadata", {})
    parsed = result.get("parsed_query", {})
    # Surface entity/community counts from metadata for frontend display
    if "fine_entity_count" not in parsed and "fine_entity_count" in metadata:
        parsed["fine_entity_count"] = metadata["fine_entity_count"]
    if "coarse_community_count" not in parsed and "coarse_community_count" in metadata:
        parsed["coarse_community_count"] = metadata["coarse_community_count"]

    return InternalQueryResponse(
        requestId=x_request_id or "internal",
        status="ok",
        answer=result.get("answer", ""),
        confidence=metadata.get("confidence", 0.0),
        mindscape_used=metadata.get("mindscape_used", False),
        details=details,
        evidence=evidence_list,
        parsed_query=parsed,
    )


# ── Federation broadcast (center → all online edge nodes) ────────────

class FederationQueryRequest(BaseModel):
    """Center node broadcasts query to all online edge nodes."""
    question: str = Field(..., min_length=1, max_length=4000)
    mode: str = Field(default="global", pattern="^(local|global|hybrid|mix|naive)$")


class FederationQueryResponse(BaseModel):
    """Aggregated response from all online edge nodes."""
    requestId: str
    status: str
    answer: str
    confidence: float = 0.0
    online_nodes: int = 0
    total_nodes: int = 0
    details: list[dict] = []
    evidence: list[dict] = []
    node_results: list[dict] = []


@router.post("/federation", response_model=FederationQueryResponse)
async def federation_query(
    body: FederationQueryRequest,
    x_federation_token: str = Header(None, alias="X-Federation-Token"),
    x_request_id: str = Header(None, alias="X-Request-Id"),
    db: Session = Depends(get_db),
):
    """
    Center node broadcasts query to all online edge nodes,
    aggregates results with judge model.
    """
    if not FEDERATION_INTERNAL_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Federation internal token not configured",
        )
    if not x_federation_token or not secrets.compare_digest(x_federation_token, FEDERATION_INTERNAL_TOKEN):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid federation token",
        )

    import asyncio
    import httpx

    manager = get_rag_manager()

    # Get all active edge nodes
    edge_nodes = db.query(Node).filter(
        Node.node_type == "edge",
        Node.status == "active",
        Node.endpoint_url.isnot(None),
    ).all()

    if not edge_nodes:
        # No edge nodes — fall back to local query_global
        result = await manager.query_global(question=body.question, mode=body.mode)
        return FederationQueryResponse(
            requestId="federation-local",
            status="ok",
            answer=result.get("answer", ""),
            confidence=result.get("metadata", {}).get("confidence", 0.0),
            online_nodes=0,
            total_nodes=0,
            evidence=result.get("evidence", []),
        )

    # Broadcast to all online edge nodes in parallel
    async def query_edge_node(node: Node) -> dict | None:
        endpoint = node.endpoint_url.rstrip("/")
        url = f"{endpoint}/api/query/internal"
        headers = {
            "Content-Type": "application/json",
            "X-Federation-Token": FEDERATION_INTERNAL_TOKEN,
        }
        payload = {
            "question": body.question,
            "mode": "mix",  # Always use "mix" to activate dual-channel retrieval
        }
        try:
            async with httpx.AsyncClient(timeout=120.0, verify=False) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    data["_node_id"] = node.node_id
                    data["_node_name"] = node.name
                    return data
                else:
                    logger.warning(f"Edge node {node.name} returned {resp.status_code}")
                    return None
        except Exception as e:
            logger.warning(f"Edge node {node.name} unreachable: {e}")
            return None

    tasks = [query_edge_node(node) for node in edge_nodes]
    results = await asyncio.gather(*tasks)
    online_results = [r for r in results if r is not None]

    if not online_results:
        return FederationQueryResponse(
            requestId="federation-no-response",
            status="error",
            answer="所有边缘节点均不可用，请检查节点状态",
            online_nodes=0,
            total_nodes=len(edge_nodes),
        )

    # Aggregate with judge model — only include nodes with meaningful answers
    _NO_CONTEXT_MARKERS = ["无法回答", "没有相关", "不包含", "未包含", "缺乏", "不存在", "无法提取", "无法推断", "无法从", "没有找到", "不具备", "超出"]
    candidates = []
    for r in online_results:
        answer = r.get("answer", "")
        confidence = r.get("confidence", 0.0)
        if not answer:
            continue
        # Skip nodes that couldn't find relevant context
        if any(marker in answer for marker in _NO_CONTEXT_MARKERS):
            continue
        # Skip nodes with very low confidence (likely irrelevant content)
        if confidence < 0.3:
            continue
        candidates.append({
            "answer": answer,
            "confidence": confidence,
            "node_name": r.get("_node_name", "unknown"),
        })

    if candidates:
        aggregated = await manager._judge_aggregate(body.question, candidates)
    else:
        aggregated = "所有节点均未找到与该问题相关的知识内容。请确认相关文档已上传至节点。"

    # Collect evidence from all nodes
    all_evidence = []
    node_results = []
    for r in online_results:
        node_results.append({
            "node_id": r.get("_node_id", ""),
            "node_name": r.get("_node_name", ""),
            "confidence": r.get("confidence", 0.0),
            "mindscape_used": r.get("mindscape_used", False),
        })
        for ev in r.get("evidence", [])[:3]:
            ev["source_node"] = r.get("_node_name", "unknown")
            all_evidence.append(ev)

    # Build details for frontend
    details = []
    for r in online_results:
        for d in r.get("details", [])[:2]:
            d["source_node"] = r.get("_node_name", "unknown")
            details.append(d)

    avg_confidence = sum(
        r.get("confidence", 0) for r in online_results
    ) / len(online_results) if online_results else 0

    return FederationQueryResponse(
        requestId=f"federation-{len(online_results)}-nodes",
        status="ok",
        answer=aggregated,
        confidence=avg_confidence,
        online_nodes=len(online_results),
        total_nodes=len(edge_nodes),
        details=details[:10],
        evidence=all_evidence[:10],
        node_results=node_results,
    )
