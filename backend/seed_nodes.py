"""
Seed script: register map nodes as real users + nodes in the database.

Usage: cd pythonproject3_mia && python seed_nodes.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from api.database import engine, SessionLocal, Base
from api.models import User, Node
from api.deps import hash_password

# ── Node definitions (matching frontend D3SandboxThreeMvp.tsx) ──────────────

NODES = [
    {"node_id": "n-registrar",  "name": "党史教育中心",       "username": "admin",          "password": "admin123456", "is_center": True, "is_admin": True},
    {"node_id": "n-simstreet",  "name": "大数据教研室",       "username": "大数据教研室",   "password": "123456"},
    {"node_id": "n-gym",        "name": "马克思理论教研室",   "username": "马克思理论教研室", "password": "123456"},
    {"node_id": "n-laoshan",    "name": "法学教研室",         "username": "法学教研室",     "password": "123456"},
    {"node_id": "n-library",    "name": "图书馆-红色经典区",  "username": "图书馆",         "password": "123456"},
    {"node_id": "n-newteach",   "name": "语言实践中心",       "username": "语言实践中心",   "password": "123456"},
]


def main():
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        created_users = 0
        created_nodes = 0

        for entry in NODES:
            node_id = entry["node_id"]
            name = entry["name"]
            username = entry["username"]
            password = entry["password"]
            is_center = entry.get("is_center", False)
            is_admin = entry.get("is_admin", False)

            # Create or skip node
            existing_node = db.query(Node).filter(Node.node_id == node_id).first()
            target_type = "center" if is_center else "edge"
            if not existing_node:
                node = Node(
                    node_id=node_id,
                    name=name,
                    node_type=target_type,
                    status="active",
                )
                db.add(node)
                created_nodes += 1
                print(f"  [+] Node: {node_id} ({name}) type={target_type}")
            else:
                # Always sync node_type and name from seed definition
                if existing_node.node_type != target_type:
                    existing_node.node_type = target_type
                    print(f"  [~] Fixed node {node_id} type -> {target_type}")
                if existing_node.name != name:
                    existing_node.name = name
                existing_node.status = "active"
                existing_node.center_application = None
                print(f"  [=] Node already exists: {node_id} ({name}) type={target_type}")

            # Create or update user
            existing_user = db.query(User).filter(User.username == username).first()
            if not existing_user:
                user = User(
                    username=username,
                    password_hash=hash_password(password),
                    role="admin" if is_admin else "user",
                    status="approved",
                    node_id=node_id,
                )
                db.add(user)
                created_users += 1
                print(f"  [+] User: {username} / {password}  (node: {node_id}, role={'admin' if is_admin else 'user'})")
            else:
                # Update existing user
                if not existing_user.node_id:
                    existing_user.node_id = node_id
                    print(f"  [~] Linked user {username} -> node {node_id}")
                if is_admin and existing_user.role != "admin":
                    existing_user.role = "admin"
                    print(f"  [~] Updated user {username} to admin role")
                if not existing_user.node_id:
                    existing_user.node_id = node_id
                print(f"  [=] User already exists: {username}")

        db.commit()
        print(f"\nDone: {created_nodes} nodes, {created_users} users created.")
        print("\nCredentials:")
        for entry in NODES:
            role = "admin" if entry.get("is_admin") else "user"
            center = " [CENTER]" if entry.get("is_center") else ""
            print(f"  {entry['username']:12s} / {entry['password']:15s}  role={role}{center}")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
