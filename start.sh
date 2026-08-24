#!/usr/bin/env bash
# MiA-RAG 后端启动脚本（API 版：不加载本地模型，嵌入走 DashScope，LLM 走 DeepSeek）
# 用法：先配置 .env（复制 .env.example 或参照 backend.env.example），然后 bash start.sh

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
export PYTHONPATH="$PWD/LightRAG:$PYTHONPATH"

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
