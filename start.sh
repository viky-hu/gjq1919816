#!/usr/bin/env bash
# ============================================================
#  密态智图 · MiA-RAG 一键启动（Linux / macOS）
#
#  用法：
#      bash start.sh
#
#  启动四个服务：
#      1. 后端主 API      backend/api/main.py        :6006
#      2. 联邦节点服务    backend/node_server.py      :6008
#      3. 中心聚合服务    frontend/central_server.py  :9000
#      4. 前端 Next.js    frontend/                  :3000
#
#  前置：
#      - backend/.env 已配置（DEEPSEEK_API_KEY / DASHSCOPE_API_KEY）
#      - 已执行 pip install -r backend/requirements-api.txt
#      - 已执行 pip install -e backend/LightRAG
#      - 已在 frontend/ 执行 pnpm install
# ============================================================

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
LOG_DIR="$ROOT/.logs"
PYTHON_BIN="${PYTHON_EXE:-python}"

BACKEND_PORT="${BACKEND_PORT:-6006}"
NODE_PORT="${NODE_PORT:-6008}"
CENTRAL_PORT="${CENTRAL_PORT:-9000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

mkdir -p "$LOG_DIR"

if [ ! -d "$BACKEND_DIR" ] || [ ! -d "$FRONTEND_DIR" ]; then
  echo "[ERR] 目录不完整：需要 backend/ 与 frontend/ 同级"
  exit 1
fi
if [ ! -f "$BACKEND_DIR/.env" ]; then
  echo "[ERR] 缺少 backend/.env"
  echo "      cp backend/.env.example backend/.env  然后填写密钥"
  exit 1
fi
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "[ERR] 前端依赖未安装"
  echo "      cd frontend && pnpm install"
  exit 1
fi
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "[ERR] 找不到 $PYTHON_BIN，请先激活虚拟环境"
  exit 1
fi
if ! command -v pnpm >/dev/null 2>&1; then
  echo "[ERR] 找不到 pnpm，请先执行 npm i -g pnpm@10.6.1"
  exit 1
fi

# ── 加载 backend/.env ─────────────────────────────────────────
set -a
# shellcheck disable=SC1091
source "$BACKEND_DIR/.env"
set +a

export DEEPSEEK_BASE_URL="${DEEPSEEK_BASE_URL:-https://api.deepseek.com/v1}"
export DEEPSEEK_MODEL="${DEEPSEEK_MODEL:-deepseek-chat}"

export EMBEDDING_API_KEY="${EMBEDDING_API_KEY:-${DASHSCOPE_API_KEY:-}}"
export EMBEDDING_BASE_URL="${EMBEDDING_BASE_URL:-https://dashscope.aliyuncs.com/compatible-mode/v1}"
export EMBEDDING_MODEL="${EMBEDDING_MODEL:-text-embedding-v3}"
export EMBEDDING_DIM="${EMBEDDING_DIM:-1024}"

export JWT_SECRET_KEY="${JWT_SECRET_KEY:-change-me-to-a-random-string}"
export FEDERATION_INTERNAL_TOKEN="${FEDERATION_INTERNAL_TOKEN:-change-me-to-a-random-shared-token}"
export FEDERATION_SM4_KEY="${FEDERATION_SM4_KEY:-mia-sm4-key-2024}"

export TIKTOKEN_CACHE_DIR="${TIKTOKEN_CACHE_DIR:-$BACKEND_DIR/data/tiktoken_cache}"
export SKIP_DOC_LOAD="${SKIP_DOC_LOAD:-1}"
export PYTHONPATH="$BACKEND_DIR/LightRAG:$BACKEND_DIR:${PYTHONPATH:-}"
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8

if [ ! -d "$TIKTOKEN_CACHE_DIR" ]; then
  echo "[ERR] 找不到 tiktoken 缓存目录：$TIKTOKEN_CACHE_DIR"
  exit 1
fi
if [ -z "${EMBEDDING_API_KEY:-}" ]; then
  echo "[WARN] EMBEDDING_API_KEY / DASHSCOPE_API_KEY 为空，检索会失败"
fi
if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
  echo "[WARN] DEEPSEEK_API_KEY 为空，问答与摘要会失败"
fi

echo "=========================================="
echo "  启动后端主 API（:$BACKEND_PORT）"
echo "=========================================="
cd "$BACKEND_DIR"
"$PYTHON_BIN" -B -m api.main --host 127.0.0.1 --port "$BACKEND_PORT" \
  >"$LOG_DIR/backend.log" 2>"$LOG_DIR/backend.err.log" &
BACKEND_PID=$!

echo "=========================================="
echo "  启动联邦节点（:$NODE_PORT）"
echo "=========================================="
"$PYTHON_BIN" -B node_server.py --host 127.0.0.1 --port "$NODE_PORT" \
  >"$LOG_DIR/node.log" 2>"$LOG_DIR/node.err.log" &
NODE_PID=$!

echo "=========================================="
echo "  启动中心聚合（:$CENTRAL_PORT）"
echo "=========================================="
cd "$FRONTEND_DIR"
"$PYTHON_BIN" -B central_server.py --port "$CENTRAL_PORT" \
  --node "local=http://127.0.0.1:$NODE_PORT" \
  >"$LOG_DIR/central.log" 2>"$LOG_DIR/central.err.log" &
CENTRAL_PID=$!

echo "=========================================="
echo "  启动前端（:$FRONTEND_PORT）"
echo "=========================================="
pnpm --filter main-platform dev -- --port "$FRONTEND_PORT" \
  >"$LOG_DIR/frontend.log" 2>"$LOG_DIR/frontend.err.log" &
FRONTEND_PID=$!

cleanup() {
  echo ""
  echo "正在停止服务 ..."
  for pid in "$FRONTEND_PID" "$CENTRAL_PID" "$NODE_PID" "$BACKEND_PID"; do
    if kill -0 "$pid" 2>/dev/null; then
      pkill -TERM -P "$pid" 2>/dev/null || true
      kill -TERM "$pid" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
  echo "已停止。"
}
trap cleanup INT TERM

wait_http() {
  local name="$1" url="$2" tries="$3"
  for _ in $(seq 1 "$tries"); do
    if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
      echo "  [OK] $name 就绪"
      return 0
    fi
    sleep 1
  done
  echo "  [注意] $name 未在 ${tries}s 内就绪，请看 .logs/"
  return 1
}

echo ""
echo "等待服务就绪 ..."
wait_http "后端 API" "http://127.0.0.1:$BACKEND_PORT/api/health" 60 || true
wait_http "联邦节点" "http://127.0.0.1:$NODE_PORT/health" 45 || true
wait_http "中心聚合" "http://127.0.0.1:$CENTRAL_PORT/health" 45 || true
wait_http "前端" "http://localhost:$FRONTEND_PORT/" 120 || true

cat <<EOF

============================================================
  启动完成
============================================================
  前端界面 : http://localhost:$FRONTEND_PORT
  后端 API : http://127.0.0.1:$BACKEND_PORT
  API 文档 : http://127.0.0.1:$BACKEND_PORT/docs
  节点服务 : http://127.0.0.1:$NODE_PORT
  中心聚合 : http://127.0.0.1:$CENTRAL_PORT
  登录账号 : admin / admin123456

  日志目录 : $LOG_DIR
  停止服务 : Ctrl+C
============================================================

EOF

wait
