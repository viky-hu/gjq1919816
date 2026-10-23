#!/usr/bin/env bash
# MiA-RAG 后端启动脚本（仅后端：主 API :6006 + 联邦节点 :6008）
# API 版：不加载本地模型，嵌入走 DashScope，LLM 走 DeepSeek
# 用法：cd backend && bash start.sh
# 前置：cp .env.example .env 并填写密钥

cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1

set -a
# 从 .env 加载真实 key / token（.env 已被 gitignore，不会提交）
if [ -f .env ]; then
  source .env
fi
set +a

# LLM 走 DeepSeek 官方（默认已是 api.deepseek.com/v1）
export DEEPSEEK_BASE_URL="${DEEPSEEK_BASE_URL:-https://api.deepseek.com/v1}"
export DEEPSEEK_MODEL="${DEEPSEEK_MODEL:-deepseek-chat}"

# 嵌入走 DashScope text-embedding-v3（需要 DASHSCOPE_API_KEY 或 EMBEDDING_API_KEY）
# EMBEDDING_API_KEY 若未在 .env 中设置，则从 DASHSCOPE_API_KEY 继承
export EMBEDDING_API_KEY="${EMBEDDING_API_KEY:-$DASHSCOPE_API_KEY}"
export EMBEDDING_BASE_URL="${EMBEDDING_BASE_URL:-https://dashscope.aliyuncs.com/compatible-mode/v1}"
export EMBEDDING_MODEL="${EMBEDDING_MODEL:-text-embedding-v3}"
export EMBEDDING_DIM="${EMBEDDING_DIM:-1024}"

# 联邦/安全配置（必须与前端 .env 一致）
export FEDERATION_INTERNAL_TOKEN="${FEDERATION_INTERNAL_TOKEN:-mia-federation-internal-token-2024}"
export FEDERATION_SM4_KEY="${FEDERATION_SM4_KEY:-mia-sm4-key-2024}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-your-production-secret-key}"

# LightRAG 使用 vendored 副本
export PYTHONPATH="$PWD/LightRAG:$PWD:$PYTHONPATH"

# ── tiktoken 词表缓存（必须）──────────────────────────────────────
# LightRAG 初始化要创建 TiktokenTokenizer("gpt-4o-mini")，需要 o200k_base 词表。
# tiktoken 的下载地址**已经失效**：
#   https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken
#   -> HTTP 404 AccountNotFound
# 因此只要本地缓存缺失，后端第一次查询就会 500，且报错与业务无关、很难排查。
# 项目已内置该词表（data/tiktoken_cache），这里指向它即可离线运行。
export TIKTOKEN_CACHE_DIR="${TIKTOKEN_CACHE_DIR:-$PWD/data/tiktoken_cache}"
if [ ! -d "$TIKTOKEN_CACHE_DIR" ]; then
  echo "[ERR] 找不到 tiktoken 缓存目录：$TIKTOKEN_CACHE_DIR"
  echo "      请确认 backend/data/tiktoken_cache 存在（含 o200k_base 词表）"
  exit 1
fi
echo "tiktoken cache: $TIKTOKEN_CACHE_DIR"

if [ -z "$EMBEDDING_API_KEY" ]; then
  echo "[WARN] EMBEDDING_API_KEY 未设置，嵌入将无法工作（API 模式需要 DashScope key）"
fi
if [ -z "$DEEPSEEK_API_KEY" ]; then
  echo "[WARN] DEEPSEEK_API_KEY 未设置，LLM 摘要/回答将无法工作"
fi

echo "Starting FastAPI (API mode) on port 6006..."
python -m api.main --host 0.0.0.0 --port 6006 &
sleep 5
echo "Starting Node Server on port 6008..."
python node_server.py --port 6008 &
echo "All services started!"
echo "FastAPI: http://0.0.0.0:6006"
echo "Node Server: http://0.0.0.0:6008"
echo "API Docs: http://0.0.0.0:6006/docs"
wait
