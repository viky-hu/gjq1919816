# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

MiA-RAG ("Mindscape-Aware RAG", based on arXiv:2512.17220) — the **backend** of a federated, multi-node, Chinese-legal-domain RAG platform. It layers a custom retrieval pipeline on top of a vendored fork of LightRAG. A "center node" federates queries across "edge nodes"; each node serves **per-user isolated** knowledge graphs.

The repo also tracks a Next.js monorepo under `frontend/` (the BFF/UI that calls these endpoints). It is tracked in git but deleted from the current working tree — the federation contract below must stay in sync with it.

## Architecture — three layers

1. **Service layer** — `api/` (FastAPI) and `node_server.py`
   - `api/main.py` is the main REST entry point (`python -m api.main`, port 6006). On startup its `lifespan` creates the SQLite schema, runs ad-hoc column migrations, seeds a default admin, loads the shared embedding model, and builds a `MiARAG` instance per approved user.
   - `node_server.py` is a separate per-node engine exposing an **SM4-encrypted** `POST /query` contract (`{"encrypted_query"}` → `{"encrypted_result"}`) plus `/health`.
   - `api/routers/` = one router per feature: `auth`, `query`, `documents`, `graph`, `nodes`, `clusters`, `macro`, `crypto`, `admin`, `chat_history`.
   - `api/database.py` (SQLite via SQLAlchemy), `api/models.py` (ORM), `api/schemas.py` (Pydantic), `api/deps.py` (JWT auth, `get_rag_manager`, `get_user_rag`).

2. **Domain layer** — `mia_emb/` (the actual MiA-RAG logic, independent of the API)
   - `mia_config.py` — `MiAConfig` dataclass: model paths, MiA-EMB prompt templates, LLM endpoint, retrieval top-k.
   - `mia_embedding.py` — `MiAEmbedding`: loads MiA-Emb-8B, implements mixed-input-attention query encoding (main + residual embeddings, score-level fusion).
   - `mindscape_summarizer.py` — two-level summarization: chunks → global "mindscape" used as retrieval context.
   - `mia_rag.py` — `MiARAG`: wraps one LightRAG instance with mindscape + dual-channel query + incremental document ingestion.
   - `dual_channel.py` — `DualChannelRetriever`: fine (entity-level vector) + coarse (graph → Leiden community) two-pass retrieval.
   - `rag_manager.py` — `MiARAGManager`: one `MiARAG` per user sharing a single embedding model/summarizer, plus cross-user `query_global` with judge-model aggregation.

3. **Vendored fork** — `LightRAG/` — the upstream graph-RAG engine (entity/relation extraction, KG storage, query modes). It has its own `LightRAG/CLAUDE.md`, `LightRAG/AGENTS.md`, and `LightRAG/.clinerules/01-basic.md`; read those for fork internals instead of re-deriving them.

**Core data flow**: document → mindscape (2-level LLM summary) → LightRAG entity/relation extraction into a KG → query → dual-channel retrieval (MiA-EMB entity match + Leiden community detection) → LLM answer + confidence → (center node) judge-model aggregation across edge nodes.

## Running

```bash
pip install -r requirements.txt          # MiA-RAG deps (LightRAG fork imported separately)
# LightRAG is vendored in ./LightRAG — install editable or add to PYTHONPATH:
pip install -e LightRAG

python -m api.main --host 0.0.0.0 --port 6006    # main REST API
python node_server.py --port 6008                 # federation node engine
bash start.sh                                     # exports env vars, starts both
```

Model weights are **not** in the repo (`models/MiA-Emb-8B` is empty) — set `MODEL_PATH` / `BASE_MODEL_PATH` to real checkpoints before starting.

Utility scripts (run from repo root):

```bash
python seed_nodes.py      # seed demo users + nodes (matches the frontend sandbox)
python fix_nodes.py       # repair node_type / user→node links
python check_docs.py      # inspect DB rows + per-user graph storage
python scripts/demo_mia_rag.py --doc-dir data/legal_docs --query "你的问题"   # CLI pipeline demo
```

Tests/lint live in the LightRAG fork (the MiA layer has no dedicated pytest suite; see `scripts/test_mia.py`):

```bash
cd LightRAG && python -m pytest tests                  # offline tests (default)
cd LightRAG && python -m pytest tests --run-integration  # requires external services
cd LightRAG && ruff check .
```

## Configuration

Runtime config is env-var driven; `start.sh` and `.env` (gitignored) set them:

- `DEEPSEEK_API_KEY` — LLM key (despite the name, the default endpoint in `mia_config.py` is Alibaba DashScope `qwen-plus`, not DeepSeek).
- `MODEL_PATH` / `BASE_MODEL_PATH` — MiA-EMB checkpoint and Qwen3-Embedding-8B base (LoRA-only dirs are auto-detected and merged via `peft`).
- `FEDERATION_INTERNAL_TOKEN` — shared node-to-node auth token (must match the frontend BFF).
- `FEDERATION_SM4_KEY` — shared 16-byte key for SM4 encryption between center and edge nodes.
- `JWT_SECRET_KEY` — JWT signing key for user auth.
- `DOC_DIR` — optional dir of `.txt` files auto-loaded into the admin user's RAG on startup.

A default `admin/admin123456` account is auto-created on first startup.

## Key patterns & gotchas

- **Per-user isolation**: each user gets an isolated LightRAG `working_dir` at `mia_rag_storage/user_<id>/`. Document dedup is a SHA-256 hash set persisted to `doc_hashes.json`; the chunk→file mapping is persisted to `chunk_file_map.json`.
- **Dual-channel only fires in "mix" mode**: `MiARAG.query` uses `DualChannelRetriever` only when `mode == "mix"` and a mindscape exists. The query routers force-remap `global`/`hybrid` → `mix` for this reason (LightRAG's native global mode is considered unreliable here).
- **Federation protocol**: center ↔ edge uses SM4-encrypted JSON with optional SM3 integrity tags (`crypto_utils.py`, `node_server.py`). The REST federation path (`POST /api/query/internal`, `POST /api/query/federation`) authenticates via an `X-Federation-Token` header with constant-time compare; edge nodes are discovered from the `nodes` table (`node_type="edge"`, `status="active"`, `endpoint_url` set).
- **Ad-hoc SQLite migrations**: `api/main.py` and `node_server.py` run raw `ALTER TABLE` statements in their lifespan before `create_all`. Adding a column to an ORM model does **not** auto-migrate an existing `mia_rag_storage/api.db` — add the corresponding migration block.
- **Comment language**: newer code comments are English, but many inline comments and log messages are Chinese; match the surrounding file's style.
- **Embedding model consistency**: MiA-EMB is a fine-tuned Qwen3-Embedding-8B (4096-dim). Changing the embedding model requires clearing each user's vector storage.
