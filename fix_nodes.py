"""
修复脚本：修正节点类型和用户关联问题。

用法：cd pythonproject3_mia && python fix_nodes.py
"""

import uuid
from api.database import SessionLocal
from api.models import Node, User

def main():
    db = SessionLocal()
    try:
        # 1. 修正 node_type: 只有 admin 关联的节点是 center
        admin = db.query(User).filter(User.username == "admin").first()
        admin_node_id = admin.node_id if admin else None

        all_nodes = db.query(Node).all()
        for node in all_nodes:
            if node.node_id == admin_node_id:
                if node.node_type != "center":
                    print(f"  [fix] {node.node_id} ({node.name}) -> center")
                    node.node_type = "center"
                node.status = "active"
            else:
                if node.node_type != "edge":
                    print(f"  [fix] {node.node_id} ({node.name}) -> edge")
                    node.node_type = "edge"
                node.status = "active"
            node.center_application = None

        # 2. 为没有 node_id 的用户创建节点
        users_without_node = db.query(User).filter(
            User.node_id.is_(None),
            User.username != "admin",
            User.status == "approved",
        ).all()

        for user in users_without_node:
            node_id = f"node-{uuid.uuid4().hex[:12]}"
            node = Node(
                node_id=node_id,
                name=user.username,
                node_type="edge",
                status="active",
            )
            db.add(node)
            user.node_id = node_id
            print(f"  [+] Created node {node_id} for user {user.username}")

        # 3. 删除孤立的 n-center 节点（旧 seed 遗留）
        orphan = db.query(Node).filter(Node.node_id == "n-center").first()
        if orphan:
            # 确认没有用户关联
            linked = db.query(User).filter(User.node_id == "n-center").first()
            if not linked:
                db.delete(orphan)
                print("  [del] Removed orphan node n-center")

        db.commit()
        print("\nDone! Current state:")
        for node in db.query(Node).all():
            print(f"  {node.node_id:20s} | {node.name:15s} | {node.node_type:7s} | {node.status}")
        for user in db.query(User).all():
            print(f"  user {user.username:12s} -> node_id={user.node_id}")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
