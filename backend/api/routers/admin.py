"""
Admin router: admin operations for managing nodes and requests.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..deps import get_current_user, get_db
from ..models import ClusterFile, Cluster, Document, Node, User
from ..schemas import ApproveUserRequest, PendingUserResponse

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(current_user: User):
    """Check if current user is admin."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin only",
        )


class AdminUserResponse(BaseModel):
    account: str
    nodeName: str
    fileCount: int
    nodeType: str  # "普通节点" | "中心节点"


class AdminRequestResponse(BaseModel):
    id: str
    account: str
    requestType: str
    remark: str
    createdAt: str


class AdminHistoryResponse(BaseModel):
    id: str
    account: str
    requestType: str
    remark: str
    approvedAt: str


class AdminSubmitRequest(BaseModel):
    requestType: str
    remark: str = ""


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all users with their node information."""
    require_admin(current_user)

    users = db.query(User).all()
    result = []
    for user in users:
        node = db.query(Node).filter(Node.node_id == user.node_id).first() if user.node_id else None
        # 文献量按 documents 表统计（该表才是真正进了检索库的文献；
        # 旧的 clusters/cluster_files 表在演示库里始终为空，会让面板一律显示 0 篇）
        file_count = (
            db.query(Document)
            .filter(Document.user_id == user.id)
            .count()
        )
        result.append(AdminUserResponse(
            account=user.username,
            nodeName=node.name if node else "未分配节点",
            fileCount=file_count,
            nodeType="中心节点" if node and node.node_type == "center" else "普通节点",
        ))
    return result


@router.get("/requests", response_model=list[AdminRequestResponse])
def list_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all pending center node applications."""
    require_admin(current_user)

    nodes = (
        db.query(Node)
        .filter(Node.status == "pending", Node.center_application.isnot(None))
        .order_by(Node.registered_at.desc())
        .all()
    )
    result = []
    for node in nodes:
        user = db.query(User).filter(User.node_id == node.node_id).first()
        result.append(AdminRequestResponse(
            id=str(node.id),
            account=user.username if user else "unknown",
            requestType="申请成为中心节点",
            remark=node.center_application or "",
            createdAt=node.registered_at.strftime("%Y-%m-%d"),
        ))
    return result


@router.get("/history", response_model=list[AdminHistoryResponse])
def list_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all approved center node applications."""
    require_admin(current_user)

    nodes = (
        db.query(Node)
        .filter(Node.node_type == "center", Node.status == "active")
        .order_by(Node.registered_at.desc())
        .all()
    )
    result = []
    for node in nodes:
        user = db.query(User).filter(User.node_id == node.node_id).first()
        result.append(AdminHistoryResponse(
            id=str(node.id),
            account=user.username if user else "unknown",
            requestType="申请成为中心节点",
            remark="",
            approvedAt=node.registered_at.strftime("%Y-%m-%d"),
        ))
    return result


@router.post("/requests")
def submit_request(
    body: AdminSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit a center node application."""
    if not current_user.node_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has no associated node",
        )

    node = db.query(Node).filter(Node.node_id == current_user.node_id).first()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    node.center_application = body.remark or f"申请类型: {body.requestType}"
    node.status = "pending"
    db.commit()

    return {"message": "Request submitted"}


@router.post("/requests/{request_id}/approve")
def approve_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Approve a center node application."""
    require_admin(current_user)

    node = db.query(Node).filter(Node.id == request_id).first()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request not found",
        )

    node.node_type = "center"
    node.status = "active"
    node.center_application = None
    db.commit()

    return {"message": "Request approved"}


# ── 用户注册审核 ─────────────────────────────────────────────────

@router.get("/pending-users", response_model=list[PendingUserResponse])
def list_pending_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all pending user registrations."""
    require_admin(current_user)

    users = (
        db.query(User)
        .filter(User.status == "pending")
        .order_by(User.created_at.desc())
        .all()
    )
    return [PendingUserResponse.model_validate(u) for u in users]


@router.post("/users/{user_id}/approve")
def approve_user(
    user_id: int,
    body: ApproveUserRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Approve or reject a user registration."""
    require_admin(current_user)

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not in pending status",
        )

    user.status = "approved" if body.approved else "rejected"

    # 审批通过时，若该账号还没有节点，自动建一个边缘节点并绑定。
    # 否则登录后 /api/macro/nodes 里没有任何节点 isHome=true，前端拿不到
    # “自身节点”，就会默认选中地图上唯一的红色中心节点（admin），
    # 于是信息栏、词云、贡献曲线全都显示成 admin 的数据。
    if body.approved and not user.node_id:
        new_node = Node(
            node_id=f"node-{uuid.uuid4().hex[:12]}",
            name=user.username,
            node_type="edge",
            status="active",
            description="注册审批通过时自动创建的节点",
        )
        db.add(new_node)
        db.flush()
        user.node_id = new_node.node_id

    db.commit()

    action = "approved" if body.approved else "rejected"
    return {"message": f"User {action}", "status": user.status, "node_id": user.node_id}
