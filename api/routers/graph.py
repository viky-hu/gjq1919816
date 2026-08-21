"""
Graph router: serve compressed knowledge graph data for frontend visualization.

Reads LightRAG's GraphML storage, compresses to target node count using
BFS from high-degree nodes, returns vis-network compatible JSON.
"""

import logging
from collections import deque
from pathlib import Path
from typing import Any

import networkx as nx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..deps import get_db, get_rag_manager
from ..models import User

logger = logging.getLogger("graph")

router = APIRouter(prefix="/api/graph", tags=["graph"])

# ── Chinese labels for entity types ──────────────────────────────────

ENTITY_TYPE_LABELS: dict[str, str] = {
    "person":          "人物",
    "organization":    "组织",
    "legal_document":  "法律文件",
    "legal_case":      "案例",
    "legal_clause":    "法条",
    "legal_concept":   "法律概念",
    "legal_procedure": "程序",
    "legal_principle": "原则",
    "location":        "地点",
    "event":           "事件",
    "data":            "数据",
    "method":          "方法",
    "artifact":        "实体",
    "concept":         "概念",
    "content":         "内容",
    "unknown":         "其他",
}

# ── Semantic color groups: 4 categories + center highlight ──────────
# Goal: reduce visual chaos from 16 entity types to 4 cohesive colors,
# with center roots receiving a distinct accent for instant recognition.

# ── Colors extracted from newgraph.html (bright & saturated) ────────
ENTITY_TYPE_COLORS: dict[str, str] = {
    "person":          "#E93B38",
    "organization":    "#FE8120",
    "legal_document":  "#1E37D1",
    "legal_case":      "#E95B90",
    "legal_clause":    "#3BDC51",
    "legal_concept":   "#04EBC7",
    "legal_procedure": "#38FC46",
    "legal_principle": "#F581F7",
    "location":        "#68DA02",
    "event":           "#1EE975",
    "data":            "#B913F9",
    "method":          "#F23D70",
    "artifact":        "#80F824",
    "concept":         "#9F0D5A",
    "content":         "#279E67",
    "unknown":         "#C58DCB",
}

CENTER_ACCENT_COLOR = "#E85D75"  # deep coral-red for center-root nodes


def _build_vis_color(entity_type: str, is_center: bool = False) -> dict[str, Any]:
    """Build vis-network color spec.
    Center roots get a high-contrast accent; others follow 4-group palette."""
    base = CENTER_ACCENT_COLOR if is_center else SEMANTIC_GROUP_COLORS.get(entity_type.lower(), "#A7AAE1")
    return {
        "background": base,
        "border": base,
        "highlight": {"background": base, "border": base},
        "hover": {"background": base, "border": base},
    }


def _load_graphml(working_dir: str) -> nx.Graph | None:
    """Load LightRAG's GraphML file from working directory."""
    graphml_path = Path(working_dir) / "graph_chunk_entity_relation.graphml"
    if not graphml_path.exists():
        return None
    try:
        G = nx.read_graphml(str(graphml_path))
        logger.info(f"Loaded GraphML from file: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
        return G
    except Exception as e:
        logger.error(f"Failed to load GraphML: {e}")
        return None


async def _load_graph_from_memory(rag) -> nx.Graph | None:
    """Try to get the graph from LightRAG's in-memory storage."""
    try:
        graph = rag.rag.chunk_entity_relation_graph._graph
        if graph is not None and graph.number_of_nodes() > 0:
            logger.info(f"Loaded graph from memory: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
            return graph
    except Exception as e:
        logger.debug(f"Could not load graph from memory: {e}")
    return None


def _compress_graph(
    G: nx.Graph,
    target_nodes: int = 300,
    min_center_trees: int = 5,
) -> tuple[set[str], list[tuple[str, str]], list[str], dict[str, int]]:
    """Compress graph to target node count using BFS from high-degree nodes.

    Returns: (kept_node_ids, kept_edges, center_root_ids, node_cluster_map)
    """
    if G.number_of_nodes() <= target_nodes:
        nodes = set(G.nodes())
        edges = list(G.edges())
        degree_sorted = sorted(nodes, key=lambda n: G.degree(n), reverse=True)
        centers = degree_sorted[:min(min_center_trees, len(degree_sorted))]
        node_cluster = {n: 0 for n in nodes}
        return nodes, edges, centers, node_cluster

    degree_map = {n: G.degree(n) for n in G.nodes()}
    degree_sorted = sorted(G.nodes(), key=lambda n: degree_map[n], reverse=True)

    center_roots = [n for n in degree_sorted if degree_map[n] >= 2][:min_center_trees]
    if len(center_roots) < min_center_trees:
        center_roots = degree_sorted[:min_center_trees]

    safe_target = max(min_center_trees * 28, target_nodes)
    tree_budget = max(28, safe_target // max(1, len(center_roots)))

    kept_nodes: set[str] = set()
    node_cluster: dict[str, int] = {}
    for ci, root in enumerate(center_roots):
        selected = {root}
        node_cluster[root] = ci
        queue = deque([(root, 0)])
        while queue and len(selected) < tree_budget:
            current, depth = queue.popleft()
            if depth >= 2:
                continue
            neighbors = list(G.neighbors(current))
            try:
                ranked = sorted(
                    neighbors,
                    key=lambda n: (
                        G.edges[current, n].get("weight", 1.0) if G.has_edge(current, n) else 1.0,
                        degree_map.get(n, 0),
                    ),
                    reverse=True,
                )
            except Exception:
                ranked = sorted(neighbors, key=lambda n: degree_map.get(n, 0), reverse=True)

            for neighbor in ranked:
                if neighbor in selected:
                    continue
                selected.add(neighbor)
                node_cluster[neighbor] = ci
                queue.append((neighbor, depth + 1))
                if len(selected) >= tree_budget:
                    break
        kept_nodes |= selected

    if len(kept_nodes) < safe_target:
        connected_candidates = [
            n for n in degree_sorted
            if n not in kept_nodes and any(nei in kept_nodes for nei in G.neighbors(n))
        ]
        for n in connected_candidates:
            kept_nodes.add(n)
            if n not in node_cluster:
                for nei in G.neighbors(n):
                    if nei in node_cluster:
                        node_cluster[n] = node_cluster[nei]
                        break
            if len(kept_nodes) >= safe_target:
                break

    if len(kept_nodes) < safe_target:
        for n in degree_sorted:
            if n not in kept_nodes:
                kept_nodes.add(n)
                # assign orphan to its highest-degree neighbor's cluster
                best_cluster = 0
                best_degree = -1
                for nei in G.neighbors(n):
                    if nei in node_cluster:
                        nd = degree_map.get(nei, 0)
                        if nd > best_degree:
                            best_degree = nd
                            best_cluster = node_cluster[nei]
                node_cluster[n] = best_cluster
                if len(kept_nodes) >= safe_target:
                    break

    if len(kept_nodes) > safe_target:
        must_keep = set(center_roots)
        optional = [n for n in degree_sorted if n in kept_nodes and n not in must_keep]
        trimmed = set(center_roots)
        for n in optional:
            trimmed.add(n)
            if len(trimmed) >= safe_target:
                break
        kept_nodes = trimmed

    kept_edges = [(u, v) for u, v in G.edges() if u in kept_nodes and v in kept_nodes]
    return kept_nodes, kept_edges, center_roots, node_cluster


CLUSTER_COLORS = ["#FEFD99", "#2FA4D7", "#FCB7C7", "#A7AAE1"]
CENTER_BORDER_COLOR = "#C0392B"  # dark red border for centers


def _build_vis_payload(
    G: nx.Graph,
    kept_nodes: set[str],
    kept_edges: list[tuple[str, str]],
    center_roots: list[str],
    target_nodes: int,
    node_cluster: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Build vis-network compatible JSON payload.

    Strategy: transform the dense semantic network into a clean
    "forest of stars" where each center root owns its own cluster.
    Cross-cluster edges are removed so barnesHut physics can push
    the four centers far apart, naturally creating fan-shaped lobes.
    """
    center_set = set(center_roots)
    subgraph = G.subgraph(kept_nodes)
    degree_map = {n: subgraph.degree(n) for n in kept_nodes}

    # ── Build nodes ──────────────────────────────────────────────────
    vis_nodes: list[dict[str, Any]] = []
    for node_id in kept_nodes:
        attrs = dict(G.nodes[node_id])
        entity_type = str(attrs.get("entity_type", "unknown")).lower()
        label = str(attrs.get("label", node_id))
        description = str(attrs.get("description", ""))
        degree = degree_map.get(node_id, 0)
        is_center = node_id in center_set
        cluster_idx = node_cluster.get(node_id, 0) if node_cluster else 0

        type_cn = ENTITY_TYPE_LABELS.get(entity_type, "其他")

        # Size: strictly within scaling.max=34
        if is_center:
            size = 34
        elif degree >= 6:
            size = 26
        elif degree >= 3:
            size = 20
        elif degree >= 2:
            size = 14
        else:
            size = 10

        # Tooltip (show real full-graph neighbors, up to 10)
        rel_lines: list[str] = []
        neighbors = list(G.neighbors(node_id))
        try:
            neighbors.sort(
                key=lambda n: float(G.edges[node_id, n].get("weight", 1.0)),
                reverse=True,
            )
        except Exception:
            pass
        for nei in neighbors[:10]:
            edge_data = G.get_edge_data(node_id, nei) or {}
            rel_desc = str(edge_data.get("description", "")).strip()
            nei_label = str(G.nodes[nei].get("label", nei))
            nei_type = str(G.nodes[nei].get("entity_type", "unknown")).lower()
            nei_type_cn = ENTITY_TYPE_LABELS.get(nei_type, "其他")
            if rel_desc:
                rel_desc = rel_desc[:80].replace("\n", " ").strip()
                rel_lines.append(f"  {label} --[{rel_desc}]--> {nei_label} ({nei_type_cn})")
            else:
                rel_lines.append(f"  {label} --> {nei_label} ({nei_type_cn})")

        tooltip = f"【{label}】\n类型：{type_cn}"
        if description:
            clean_desc = description[:200].replace("\n", " ").strip()
            if clean_desc:
                tooltip += f"\n描述：{clean_desc}"
        tooltip += f"\n连接数：{degree}"
        if rel_lines:
            tooltip += "\n\n关系：" + "\n" + "\n".join(rel_lines)
            if len(neighbors) > 10:
                tooltip += f"\n  ...等共 {len(neighbors)} 条关系"

        short_label = label[:8]

        # Color by entity_type — bright palette, centers included
        base = ENTITY_TYPE_COLORS.get(entity_type, "#A7AAE1")
        color_spec = {
            "background": base,
            "border": base,
            "highlight": {"background": base, "border": base},
            "hover": {"background": base, "border": base},
        }

        vis_nodes.append({
            "id": node_id,
            "label": short_label,
            "title": tooltip,
            "color": color_spec,
            "shape": "dot",
            "size": size,
            "borderWidth": 1.5 if not is_center else 2.5,
        })

    # ── Build edges: forest-of-stars filtering ────────────────────────
    # Keep ONLY intra-cluster edges. Remove center-to-center edges
    # and all cross-cluster edges. This lets barnesHut push the four
    # centers far apart without elastic ropes pulling them back together.
    vis_edges: list[dict[str, Any]] = []
    for u, v in kept_edges:
        # Drop center-to-center edges entirely
        if u in center_set and v in center_set:
            continue

        # Drop cross-cluster edges entirely
        u_cluster = node_cluster.get(u) if node_cluster else None
        v_cluster = node_cluster.get(v) if node_cluster else None
        if u_cluster is None or v_cluster is None or u_cluster != v_cluster:
            continue

        # Intra-cluster edge: thin, subtle, uniform
        edge_data = G.get_edge_data(u, v) or {}
        description = str(edge_data.get("description", ""))
        from_label = str(G.nodes[u].get("label", u))
        to_label = str(G.nodes[v].get("label", v))

        edge_title = f"{from_label} → {to_label}"
        if description:
            clean_desc = description[:100].replace("\n", " ").strip()
            if clean_desc:
                edge_title += f"\n{clean_desc}"

        vis_edges.append({
            "from": u,
            "to": v,
            "width": 1.2,
            "title": edge_title,
            "color": "rgba(0,71,255,0.30)",
        })

    # Filter out isolated nodes (no edges after topology cleaning)
    connected_node_ids = set()
    for e in vis_edges:
        connected_node_ids.add(e["from"])
        connected_node_ids.add(e["to"])
    vis_nodes = [n for n in vis_nodes if n["id"] in connected_node_ids]

    # Render largest nodes first so they sit on top of smaller ones
    vis_nodes.sort(key=lambda n: n["size"], reverse=True)

    center_labels = []
    for root in center_roots:
        if root in G.nodes():
            center_labels.append(str(G.nodes[root].get("label", root)))

    return {
        "meta": {
            "sourceNodeCount": G.number_of_nodes(),
            "sourceEdgeCount": G.number_of_edges(),
            "keptNodeCount": len(vis_nodes),
            "keptEdgeCount": len(vis_edges),
            "targetNodeCount": target_nodes,
            "centerRoots": center_labels,
        },
        "nodes": vis_nodes,
        "edges": vis_edges,
    }


@router.get("")
async def get_knowledge_graph(
    account: str = Query(default="", description="User account (defaults to first approved user)"),
    targetNodes: int = Query(default=300, ge=50, le=2000, description="Target node count"),
    db: Session = Depends(get_db),
):
    """Get compressed knowledge graph for visualization."""
    manager = get_rag_manager()

    target_user = None
    if account:
        target_user = db.query(User).filter(User.username == account).first()
    if not target_user:
        target_user = db.query(User).filter(User.status == "approved").first()
    if not target_user:
        raise HTTPException(status_code=404, detail="No approved user found")

    try:
        rag = await manager.get_user_rag(target_user.id)
        working_dir = rag.working_dir
    except Exception as e:
        logger.error(f"Failed to get RAG for user {target_user.id}: {e}")
        raise HTTPException(status_code=500, detail=f"RAG initialization failed: {e}")

    G = await _load_graph_from_memory(rag)
    if G is None or G.number_of_nodes() == 0:
        G = _load_graphml(working_dir)
    if G is None or G.number_of_nodes() == 0:
        return {
            "meta": {
                "sourceNodeCount": 0,
                "sourceEdgeCount": 0,
                "keptNodeCount": 0,
                "keptEdgeCount": 0,
                "targetNodeCount": targetNodes,
                "centerRoots": [],
            },
            "nodes": [],
            "edges": [],
        }

    kept_nodes, kept_edges, center_roots, node_cluster = _compress_graph(
        G, target_nodes=targetNodes
    )

    payload = _build_vis_payload(G, kept_nodes, kept_edges, center_roots, targetNodes, node_cluster)
    return payload
