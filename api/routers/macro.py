"""
Macro router: macro platform data APIs for dashboard visualization.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db
from ..models import Cluster, ClusterFile, Document, Node, QueryLog, User

router = APIRouter(prefix="/api/macro", tags=["macro"])

# ── Endpoints ─────────────────────────────────────────────────────────


@router.get("/nodes")
def get_macro_nodes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all nodes with their positions and metrics for 3D map visualization."""
    from datetime import timedelta
    from sqlalchemy import func

    nodes = db.query(Node).filter(Node.status.in_(["active", "pending"])).all()
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)

    result = []
    for i, node in enumerate(nodes):
        radius = 8
        x = radius * (i % 3 - 1)
        z = radius * (i // 3 - 1)

        user = db.query(User).filter(User.node_id == node.node_id).first()
        if user:
            total_queries = (
                db.query(func.count(QueryLog.id))
                .filter(QueryLog.user_id == user.id)
                .scalar()
            ) or 0
            today_queries = (
                db.query(func.count(QueryLog.id))
                .filter(QueryLog.user_id == user.id, QueryLog.created_at >= today_start)
                .scalar()
            ) or 0
            week_queries = (
                db.query(func.count(QueryLog.id))
                .filter(QueryLog.user_id == user.id, QueryLog.created_at >= week_ago)
                .scalar()
            ) or 0
            activity = min(100, round(week_queries * 3.5))
        else:
            total_queries = 0
            today_queries = 0
            activity = 0

        connection_count = max(0, len(nodes) - 1)
        display_label = user.username if user else node.name

        result.append({
            "id": node.node_id,
            "label": display_label,
            "labelCode": f"SECTOR-{i+1:02d}",
            "position": [x, 0, z],
            "isHome": node.node_id == current_user.node_id,
            "nodeType": node.node_type,
            "metrics": {
                "activity": activity,
                "connections": connection_count,
                "totalRecords": total_queries,
                "todayUpdates": today_queries,
                "callCount": total_queries,
                "uptime": 99.8,
            },
        })

    # No mock fallback: empty DB means empty nodes list.
    return {"nodes": result}


@router.get("/file-count")
def get_file_count(
    account: str = Query(""),
    db: Session = Depends(get_db),
):
    """Get file count for a user by account name (internal use, no JWT required)."""
    if not account:
        return {"total_files": 0, "cluster_count": 0}

    user = db.query(User).filter(User.username == account).first()
    if not user:
        return {"total_files": 0, "cluster_count": 0}

    cluster_count = db.query(Cluster).filter(Cluster.user_id == user.id).count()
    cluster_file_count = (
        db.query(ClusterFile)
        .join(Cluster)
        .filter(Cluster.user_id == user.id)
        .count()
    )
    doc_count = db.query(Document).filter(Document.user_id == user.id).count()
    total_files = cluster_file_count + doc_count

    # No mock fallback: report the true counts (0 when nothing stored).
    return {"total_files": total_files, "cluster_count": cluster_count}


@router.get("/search-frequency")
def get_search_frequency(
    period: str = Query("today", pattern="^(today|week|month|quarter|year)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get search frequency ranking by period."""
    now = datetime.now(timezone.utc)

    if period == "today":
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start_time = now - timedelta(days=7)
    elif period == "month":
        start_time = now - timedelta(days=30)
    elif period == "quarter":
        start_time = now - timedelta(days=90)
    else:
        start_time = now - timedelta(days=365)

    from sqlalchemy import func
    all_users = db.query(User).all()

    seen_names: set[str] = set()
    unique_users = []
    for user in all_users:
        if user.username not in seen_names:
            seen_names.add(user.username)
            unique_users.append(user)

    result = []
    for user in unique_users:
        user_ids = [u.id for u in all_users if u.username == user.username]
        count = (
            db.query(func.count(QueryLog.id))
            .filter(
                QueryLog.user_id.in_(user_ids),
                QueryLog.created_at >= start_time,
            )
            .scalar()
        ) or 0
        result.append({"name": user.username, "value": count})

    result.sort(key=lambda x: (-x["value"], x["name"]))
    result = result[:5]

    # No mock fallback: empty queries means empty rankings.
    return {"period": period, "rankings": result}


@router.get("/node-contributions")
def get_node_contributions(
    period: str = Query("recent", pattern="^(recent|24h|7d|30d)$"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get node contribution curves over time."""
    now = datetime.now(timezone.utc)

    if period == "24h":
        start_time = now - timedelta(hours=24)
        intervals = 7
    elif period == "7d":
        start_time = now - timedelta(days=7)
        intervals = 7
    elif period == "30d":
        start_time = now - timedelta(days=30)
        intervals = 7
    else:
        start_time = now - timedelta(days=1)
        intervals = 5

    from sqlalchemy import func

    nodes = db.query(Node).filter(Node.status.in_(["active", "pending"])).all()

    result = {}
    for node in nodes:
        user = db.query(User).filter(User.node_id == node.node_id).first()
        if not user:
            continue

        interval_duration = (now - start_time) / intervals
        series = []
        for i in range(intervals):
            interval_start = start_time + interval_duration * i
            interval_end = start_time + interval_duration * (i + 1)
            query_count = (
                db.query(func.count(QueryLog.id))
                .filter(
                    QueryLog.user_id == user.id,
                    QueryLog.created_at >= interval_start,
                    QueryLog.created_at < interval_end,
                )
                .scalar()
            ) or 0
            series.append(query_count)

        result[node.node_id] = {
            "label": node.name,
            "series": series,
        }

    if not result:
        users = db.query(User).filter(User.role != "admin").all()
        for user in users:
            interval_duration = (now - start_time) / intervals
            series = []
            for i in range(intervals):
                interval_start = start_time + interval_duration * i
                interval_end = start_time + interval_duration * (i + 1)
                count = (
                    db.query(func.count(QueryLog.id))
                    .filter(
                        QueryLog.user_id == user.id,
                        QueryLog.created_at >= interval_start,
                        QueryLog.created_at < interval_end,
                    )
                    .scalar()
                ) or 0
                series.append(count)
            if any(s > 0 for s in series):
                result[f"user-{user.id}"] = {
                    "label": user.username,
                    "series": series,
                }

    # No mock fallback: empty data means empty contributions.
    return {"period": period, "contributions": result}


@router.get("/word-cloud")
def get_word_cloud(
    node_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get word cloud data from knowledge graph entities for a specific node."""
    word_freq: dict[str, int] = {}

    target_user = None
    if node_id:
        target_user = db.query(User).filter(User.node_id == node_id).first()

    # Try to get entities from LightRAG knowledge graph
    try:
        from ..deps import get_rag_manager
        manager = get_rag_manager()

        if target_user:
            target_user_ids = [target_user.id]
        elif node_id:
            target_user_ids = list(manager._user_rags.keys())
        else:
            target_user_ids = list(manager._user_rags.keys())

        for uid in target_user_ids:
            rag = manager._user_rags.get(uid)
            if rag and rag.rag and hasattr(rag.rag, "chunk_entity_relation_graph"):
                graph = rag.rag.chunk_entity_relation_graph._graph
                if graph:
                    for node in graph.nodes():
                        attrs = dict(graph.nodes[node])
                        label = str(attrs.get("label", node)).strip()
                        if len(label) >= 2:
                            word_freq[label] = word_freq.get(label, 0) + graph.degree(node)
    except Exception as e:
        import logging
        logging.getLogger("macro").warning(f"word-cloud RAG query failed: {e}")

    # Fallback 1: extract from document filenames
    if not word_freq:
        import jieba
        doc_query = db.query(Document)
        if target_user:
            doc_query = doc_query.filter(Document.user_id == target_user.id)
        recent_docs = doc_query.order_by(Document.uploaded_at.desc()).limit(50).all()
        for doc in recent_docs:
            if not doc.filename:
                continue
            words = jieba.cut(doc.filename)
            for word in words:
                word = word.strip()
                if len(word) >= 2:
                    word_freq[word] = word_freq.get(word, 0) + 1

    # Fallback 2: extract from query logs
    if not word_freq and target_user:
        recent_queries = (
            db.query(QueryLog)
            .filter(QueryLog.user_id == target_user.id)
            .order_by(QueryLog.created_at.desc())
            .limit(100)
            .all()
        )
        import jieba
        for query in recent_queries:
            if not query.question:
                continue
            words = jieba.cut(query.question)
            for word in words:
                word = word.strip()
                if len(word) >= 2:
                    word_freq[word] = word_freq.get(word, 0) + 1

    # Sort and build response
    sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:30]

    # No mock fallback: empty graph means empty word cloud.
    if sorted_words:
        max_weight = sorted_words[0][1]
        word_cloud = [
            {"text": word, "weight": max(30, int(98 * count / max_weight))}
            for word, count in sorted_words
        ]
    else:
        word_cloud = []

    return {"nodeId": node_id, "words": word_cloud}


@router.get("/updates")
def get_updates(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get recent updates timeline."""
    updates = []

    clusters = (
        db.query(Cluster)
        .order_by(Cluster.created_at.desc())
        .limit(limit // 2)
        .all()
    )
    for cluster in clusters:
        user = db.query(User).filter(User.id == cluster.user_id).first()
        updates.append({
            "id": f"cluster-{cluster.id}",
            "actor": user.username if user else "unknown",
            "action": f"新建了聚类《{cluster.name}》",
            "type": "cluster",
            "createdAt": cluster.created_at.isoformat(),
        })

    files = (
        db.query(ClusterFile)
        .order_by(ClusterFile.uploaded_at.desc())
        .limit(limit // 2)
        .all()
    )
    for file in files:
        cluster = db.query(Cluster).filter(Cluster.id == file.cluster_id).first()
        user = db.query(User).filter(User.id == cluster.user_id).first() if cluster else None
        updates.append({
            "id": f"file-{file.id}",
            "actor": user.username if user else "unknown",
            "action": f"上传了文件《{file.filename}》",
            "type": "file",
            "createdAt": file.uploaded_at.isoformat(),
        })

    updates.sort(key=lambda x: x["createdAt"], reverse=True)
    updates = updates[:limit]

    # No mock fallback: no clusters/files means empty updates.
    return {"updates": updates}
