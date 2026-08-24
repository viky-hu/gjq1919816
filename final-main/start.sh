#!/usr/bin/env bash
# ============================================================
# MiA-RAG 一键启动脚本（前后端）
#
# 功能：
#   - 后端（FastAPI, port 6006）：API 模式（嵌入走 DashScope、LLM 走 DeepSeek），
#     启动时【不触发文档全量加载】（SKIP_DOC_LOAD=1）——文档由前端上传时动态入库。
#   - 前端（Next.js dev, port 3000）：连接本地后端。
#
# 用法：
#   bash start.sh
#
# 前置：
#   - pythonproject3_mia/.env 已配置真实 key（DEEPSEEK_API_KEY / DASHSCOPE_API_KEY）
#   - 已执行过 pnpm install
# ============================================================

set -euo pipefail

# ── 路径定位 ────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/../pythonproject3_mia"   # 后端目录（本脚本在 final-main/ 下）

if [ ! -d "$BACKEND_DIR" ]; then
  echo "[ERR] 未找到后端目录: $BACKEND_DIR"
  echo "      请确认目录结构为:"
  echo "        final-main/           (本脚本所在)"
  echo "        pythonproject3_mia/   (后端)"
  exit 1
fi

# ── 加载后端 .env（真实 key / token）─────────────────────
set -a
if [ -f "$BACKEND_DIR/.env" ]; then
  source "$BACKEND_DIR/.env"
else
  echo "[WARN] $BACKEND_DIR/.env 不存在，将使用默认值（key 可能缺失）"
fi
set +a

# ── 后端环境变量（API 模式）───────────────────────────────
export DEEPSEEK_BASE_URL="${DEEPSEEK_BASE_URL:-https://api.deepseek.com/v1}"
export DEEPSEEK_MODEL="${DEEPSEEK_MODEL:-deepseek-chat}"

# 嵌入走 DashScope text-embedding-v3
export EMBEDDING_API_KEY="${EMBEDDING_API_KEY:-$DASHSCOPE_API_KEY}"
export EMBEDDING_BASE_URL="${EMBEDDING_BASE_URL:-https://dashscope.aliyuncs.com/compatible-mode/v1}"
export EMBEDDING_MODEL="${EMBEDDING_MODEL:-text-embedding-v3}"
export EMBEDDING_DIM="${EMBEDDING_DIM:-1024}"

# 联邦/安全（必须与前端 .env 一致）
export FEDERATION_INTERNAL_TOKEN="${FEDERATION_INTERNAL_TOKEN:-mia-federation-internal-token-2024}"
export FEDERATION_SM4_KEY="${FEDERATION_SM4_KEY:-mia-sm4-key-2024}"
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-your-production-secret-key}"

# 启动时不触发文档全量加载（文档由前端上传时动态入库）
export SKIP_DOC_LOAD=1

# LightRAG 使用 vendored 副本
export PYTHONPATH="$BACKEND_DIR/LightRAG:$BACKEND_DIR:${PYTHONPATH:-}"

# ── 校验 key ──────────────────────────────────────────────
if [ -z "$EMBEDDING_API_KEY" ]; then
  echo "[WARN] EMBEDDING_API_KEY 未设置，嵌入将无法工作（需 DashScope key）"
fi
if [ -z "$DEEPSEEK_API_KEY" ]; then
  echo "[WARN] DEEPSEEK_API_KEY 未设置，LLM 摘要/回答将无法工作"
fi

# ── 启动后端 ──────────────────────────────────────────────
echo "=========================================="
echo "  启动后端 (FastAPI :6006, SKIP_DOC_LOAD)"
echo "=========================================="
cd "$BACKEND_DIR"
python -m api.main --host 0.0.0.0 --port 6006 > /tmp/mia_backend.log 2>&1 &
BACKEND_PID=$!
echo "  后端 PID: $BACKEND_PID (日志: /tmp/mia_backend.log)"

# ── 启动前端 ──────────────────────────────────────────────
echo "=========================================="
echo "  启动前端 (Next.js :3000)"
echo "=========================================="
cd "$SCRIPT_DIR"
pnpm --filter main-platform dev > /tmp/mia_frontend.log 2>&1 &
FRONTEND_PID=$!
echo "  前端 PID: $FRONTEND_PID (日志: /tmp/mia_frontend.log)"

# ── 等待后端就绪 ─────────────────────────────────────────
echo ""
echo "等待后端就绪..."
for i in $(seq 1 30); do
  if curl -s --max-time 2 http://127.0.0.1:6006/api/health 2>/dev/null | grep -q "model_loaded"; then
    echo "  ✓ 后端就绪"
    break
  fi
  if [ $i -eq 30 ]; then
    echo "  [WARN] 后端 30s 未就绪，请查看 /tmp/mia_backend.log"
  fi
  sleep 1
done

# ── 等待前端就绪 ─────────────────────────────────────────
echo "等待前端就绪..."
for i in $(seq 1 60); do
  if curl -s --max-time 2 -o /dev/null -w "%{http_code}" http://localhost:3000/ 2>/dev/null | grep -q "200"; then
    echo "  ✓ 前端就绪"
    break
  fi
  if [ $i -eq 60 ]; then
    echo "  [WARN] 前端 60s 未就绪，请查看 /tmp/mia_frontend.log"
  fi
  sleep 1
done

# ── 完成 ─────────────────────────────────────────────────
echo ""
echo "=========================================="
echo "  全部服务已启动！"
echo "  前端:   http://localhost:3000"
echo "  后端:   http://localhost:6006"
echo "  API文档: http://localhost:6006/docs"
echo "  后端日志: /tmp/mia_backend.log"
echo "  前端日志: /tmp/mia_frontend.log"
echo "  停止:   kill $BACKEND_PID $FRONTEND_PID  (或 Ctrl+C)"
echo "=========================================="

# 保持前台等待（Ctrl+C 停止全部）
wait
