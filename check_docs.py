"""Check if documents are in the database and graph."""
import sqlite3, json, os

DB = "mia_rag_storage/api.db"
conn = sqlite3.connect(DB)
c = conn.cursor()

print("=== Documents in DB ===")
for r in c.execute("SELECT id, user_id, filename, status FROM documents ORDER BY id DESC LIMIT 20"):
    print(f"  {r}")

print("\n=== Users ===")
for r in c.execute("SELECT id, username, node_id FROM users"):
    print(f"  {r}")

print("\n=== Per-user RAG storage ===")
base = "mia_rag_storage"
if os.path.isdir(base):
    for d in sorted(os.listdir(base)):
        path = os.path.join(base, d)
        if os.path.isdir(path):
            files = os.listdir(path)
            graph_file = os.path.join(path, "graph_chunk_entity_relation.graphml")
            graph_size = os.path.getsize(graph_file) if os.path.exists(graph_file) else 0
            doc_hashes_file = os.path.join(path, "doc_hashes.json")
            hash_count = 0
            if os.path.exists(doc_hashes_file):
                try:
                    hash_count = len(json.load(open(doc_hashes_file)))
                except: pass
            print(f"  {d}: {len(files)} files, graphml={graph_size}B, doc_hashes={hash_count}")

conn.close()
