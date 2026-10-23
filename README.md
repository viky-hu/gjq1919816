# 密态智图 · MiA-RAG 联邦知识图谱协同检索平台

面向中文法律与机构知识库的**多节点联邦检索系统**。每个节点维护自己的知识图谱，查询时由节点独立检索，再经中心聚合层裁决后返回答案；节点之间使用 SM4 加密传输，用户数据按账号隔离。

本提交包为 **API 模式**版本：嵌入走 DashScope（`text-embedding-v3`），摘要与问答走 DeepSeek，**不包含本地模型权重，也不需要 GPU**。

---

## 1. 技术栈

### 后端

| 类别 | 选型 |
| --- | --- |
| 语言 | Python 3.10+ |
| Web 框架 | FastAPI + Uvicorn |
| ORM / 数据库 | SQLAlchemy + SQLite（`backend/mia_rag_storage/api.db`） |
| 图谱检索引擎 | LightRAG（`backend/LightRAG`，vendored 源码） |
| 检索算法 | MiA-EMB 双通道检索：实体级向量召回 + Leiden/Louvain 社区粗召回 |
| 摘要与生成 | OpenAI 兼容接口（默认 DeepSeek `deepseek-chat`） |
| Embedding | DashScope OpenAI 兼容接口（默认 `text-embedding-v3`，1024 维） |
| 联邦安全 | SM4 对称加密、SM3 完整性校验、JWT 鉴权 |
| 文档处理 | PyMuPDF、Pillow、pytesseract、OpenCV（可选） |
| 图算法 | NetworkX、python-louvain |
| 中文分词 | jieba |

### 前端

| 类别 | 选型 |
| --- | --- |
| 框架 | Next.js 16（App Router）+ React 19 |
| 语言 | TypeScript |
| 样式 | Tailwind CSS v4 + Radix UI |
| 动效 / 可视化 | GSAP、Three.js / React Three Fiber、D3 |
| 状态与请求 | React Server/Client Components、BFF Route Handlers |
| 数据库 | PostgreSQL + Prisma 5（聊天历史、集群文件） |
| 工程化 | pnpm 10.6.1 workspace + Turborepo |
| 中心聚合服务 | `frontend/central_server.py`（FastAPI，端口 9000） |

### 运行时组成

| 服务 | 目录 | 默认端口 | 作用 |
| --- | --- | --- | --- |
| 前端 BFF + UI | `frontend/` | 3000 | 页面、登录、聊天、数据库与宏观可视化 |
| 主 API | `backend/api/main.py` | 6006 | 用户、文档、图谱、查询、集群、管理员接口 |
| 联邦节点 | `backend/node_server.py` | 6008 | SM4 加密的 `/query` 节点检索契约 |
| 中心聚合 | `frontend/central_server.py` | 9000 | 把查询分发到各节点并聚合裁决 |

---

## 2. 目录结构

```text
pythonproject3_mia/
├── backend/                      # Python 后端
│   ├── api/                      # FastAPI 应用与各功能路由
│   │   ├── main.py               # 主入口（:6006）
│   │   ├── database.py           # SQLite / SQLAlchemy
│   │   ├── models.py             # ORM 模型
│   │   ├── schemas.py            # Pydantic 模型
│   │   ├── deps.py               # JWT、依赖注入
│   │   └── routers/              # auth / query / documents / graph / nodes ...
│   ├── mia_emb/                  # MiA-RAG 领域层
│   │   ├── mia_config.py         # 配置
│   │   ├── mia_embedding.py      # 本地模型 / API 双模式嵌入
│   │   ├── api_embedding.py      # DashScope 嵌入
│   │   ├── mindscape_summarizer.py
│   │   ├── dual_channel.py       # 双通道检索
│   │   ├── rag_manager.py        # 按用户隔离的 RAG 实例
│   │   └── multimodal/           # PDF / 图片 / 视频处理
│   ├── LightRAG/                 # vendored LightRAG（含 LICENSE）
│   ├── data/
│   │   ├── legal_docs/           # 演示文档
│   │   └── tiktoken_cache/       # 内置 o200k_base 词表（离线可用）
│   ├── scripts/                  # 演示、基准与自检脚本
│   ├── node_server.py            # 联邦节点服务（:6008）
│   ├── crypto_utils.py           # SM2 / SM3 / SM4 工具
│   ├── seed_nodes.py             # 写入演示节点与账号
│   ├── requirements.txt          # 全量依赖（含本地模型）
│   ├── requirements-api.txt      # API 模式依赖（推荐）
│   └── .env.example
├── frontend/                     # Next.js 前端 Monorepo
│   ├── apps/main-platform/       # 主平台
│   │   ├── app/                  # 页面、窗口、BFF 路由
│   │   ├── prisma/               # 数据库 schema 与迁移
│   │   └── public/               # 静态资源
│   ├── packages/                 # 共享 UI 与 TS 配置
│   ├── central_server.py         # 中心聚合服务（:9000）
│   └── apps/main-platform/.env.example
├── docs/GIT_WORKFLOW.md          # 团队分支与提交规范
├── start.ps1                     # Windows 一键启动 / 停止
├── start.sh                      # Linux / macOS 一键启动
└── README.md
```

---

## 3. 运行环境

- **Python** 3.10 或 3.11
- **Node.js** ≥ 20.9（Next.js 16 要求）
- **pnpm** 10.6.1（`npm i -g pnpm@10.6.1`）
- **PostgreSQL** 14+（可选，用于聊天历史持久化；不装可用内存模式）
- **API Key**：DeepSeek（问答/摘要）+ DashScope（嵌入）
- 不需要 GPU，也不需要下载模型权重

> 首次启动会创建 SQLite 数据库和管理员账号，默认 `admin / admin123456`，登录后请尽快修改。

---

## 4. 快速开始

### 4.1 安装后端依赖

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r backend\requirements-api.txt
pip install -e backend\LightRAG
```

Linux / macOS：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r backend/requirements-api.txt
pip install -e backend/LightRAG
```

> `pip install -e backend/LightRAG` 会安装 vendored LightRAG 的第三方依赖。启动脚本同时会把 `backend/LightRAG` 加入 `PYTHONPATH`。

### 4.2 配置环境变量

```powershell
copy backend\.env.example backend\.env
copy frontend\apps\main-platform\.env.example frontend\apps\main-platform\.env.local
```

至少填写：

- `backend/.env`：`DEEPSEEK_API_KEY`、`DASHSCOPE_API_KEY`（或 `EMBEDDING_API_KEY`）
- `frontend/apps/main-platform/.env.local`：`DATABASE_URL`（使用 PostgreSQL 时）、`FEDERATION_INTERNAL_TOKEN`、`FEDERATION_SM4_KEY`

两边的 `FEDERATION_INTERNAL_TOKEN` 与 `FEDERATION_SM4_KEY` **必须完全一致**。SM4 密钥按 16 字节使用，长度不足会自动补齐。

### 4.3 安装前端依赖

```powershell
cd frontend
pnpm install
pnpm --filter main-platform db:generate
```

如果使用 PostgreSQL，再执行迁移：

```powershell
pnpm --filter main-platform db:deploy
```

没有 PostgreSQL 时，把 `CHAT_HISTORY_STORAGE_MODE` 设为 `mock`，跳过迁移即可；设为 `auto` 则会优先使用数据库、失败后自动降级。

### 4.4 一键启动

Windows：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Linux / macOS：

```bash
bash start.sh
```

脚本会依次启动：

1. 主 API `http://127.0.0.1:6006`
2. 联邦节点 `http://127.0.0.1:6008`
3. 中心聚合 `http://127.0.0.1:9000`
4. 前端 `http://localhost:3000`

停止：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1 -Stop
```

### 4.5 访问

| 地址 | 说明 |
| --- | --- |
| `http://localhost:3000` | 前端界面 |
| `http://127.0.0.1:6006/docs` | 后端 Swagger 文档 |
| `http://127.0.0.1:6006/api/health` | 后端健康检查 |
| `http://127.0.0.1:6008/health` | 节点健康检查 |
| `http://127.0.0.1:9000/health` | 中心聚合健康检查 |

默认管理员：`admin / admin123456`。

---

## 5. 手动启动（不使用一键脚本）

分别在四个终端中执行：

```bash
# 终端 1：主 API
cd backend
set -a; source .env; set +a
export PYTHONPATH="$PWD/LightRAG:$PWD"
export TIKTOKEN_CACHE_DIR="$PWD/data/tiktoken_cache"
python -m api.main --host 127.0.0.1 --port 6006

# 终端 2：联邦节点
cd backend
set -a; source .env; set +a
export PYTHONPATH="$PWD/LightRAG:$PWD"
python node_server.py --host 127.0.0.1 --port 6008

# 终端 3：中心聚合
cd frontend
python central_server.py --port 9000 --node local=http://127.0.0.1:6008

# 终端 4：前端
cd frontend
pnpm --filter main-platform dev
```

Windows 下把 `set -a; source .env; set +a` 换成在 `start.ps1` 中同样的环境变量加载方式，或在 PowerShell 中逐项 `$env:NAME="value"`。

---

## 6. 关键配置说明

### 后端 `backend/.env`

| 变量 | 说明 |
| --- | --- |
| `DEEPSEEK_API_KEY` | LLM 密钥（摘要、问答） |
| `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL` | OpenAI 兼容地址与模型名 |
| `DASHSCOPE_API_KEY` | DashScope 密钥；未单独设置 `EMBEDDING_API_KEY` 时自动继承 |
| `EMBEDDING_API_KEY` | 设置后进入 API 嵌入模式，无需本地权重 |
| `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` / `EMBEDDING_DIM` | 嵌入接口配置 |
| `JWT_SECRET_KEY` | 登录令牌签名密钥，生产环境务必替换 |
| `FEDERATION_INTERNAL_TOKEN` | 服务间鉴权令牌 |
| `FEDERATION_SM4_KEY` | 联邦链路 SM4 共享密钥（16 字节） |
| `TIKTOKEN_CACHE_DIR` | 词表缓存目录，不填时启动脚本指向 `backend/data/tiktoken_cache` |
| `SKIP_DOC_LOAD` | `1` 表示启动时不自动导入 `data/legal_docs` |
| `VL_ENABLED` / `VL_MODEL` | 可选的图片/视频描述模型 |

### 前端 `frontend/apps/main-platform/.env.local`

| 变量 | 说明 |
| --- | --- |
| `DATABASE_URL` | PostgreSQL 连接串（Prisma） |
| `CHAT_HISTORY_STORAGE_MODE` | `prisma` / `auto` / `mock` |
| `FEDERATION_CENTRAL_BASE_URL` | 中心聚合服务地址，默认 `http://127.0.0.1:9000` |
| `MIA_RAG_NODE_URL` | 主 API 地址，默认 `http://127.0.0.1:6006`（BFF 的 `/api/query/internal`、`/api/sm4/*`、`/api/graph` 等路由走这里；6008 的节点服务只供中心聚合调用） |
| `NEXT_PUBLIC_MIA_RAG_AUTH_URL` | 主 API 地址，默认 `http://127.0.0.1:6006` |
| `FEDERATION_INTERNAL_TOKEN` | 必须与后端一致 |
| `FEDERATION_SM4_KEY` | 必须与后端一致 |
| `FEDERATION_REQUIRE_TLS` | 本地 HTTP 联调设为 `false` |
| `NODE_AUTH_STRICT_MODE` | 本地演示若遇鉴权问题可临时设为 `false` |

---

## 7. 检索与联邦链路

```text
上传文档
  → 文本抽取 / 多模态解析
  → 两级 mindscape 摘要
  → LightRAG 实体与关系抽取，写入按用户隔离的知识图谱
  → 查询
      ├─ 实体级向量召回（MiA-EMB）
      └─ 图社区粗召回（Louvain / Leiden）
  → 融合排序 → LLM 生成答案 + 置信度
  → 联邦模式：中心聚合服务将查询分发到各节点
               （SM4 加密传输，SM3 完整性校验）
  → 聚合裁决后返回前端
```

每个账号拥有独立的 `backend/mia_rag_storage/user_<id>/` 图谱目录，文档去重使用 SHA-256，分块与文件映射单独持久化。

---

## 8. 数据与模型

- 本包**不包含模型权重**。API 模式使用 DashScope 嵌入 + DeepSeek 生成。
- `backend/LightRAG` 为 vendored 源码，遵循其 MIT 许可证（见 `backend/LightRAG/LICENSE`）。
- `backend/data/legal_docs` 为演示文档，可在首次启动时导入。
- `backend/data/tiktoken_cache` 已内置 `o200k_base` 词表，避免因官方下载地址失效导致首次查询 500。
- 运行数据（SQLite、上传文件、向量库）均被 `.gitignore` 排除，不会进入仓库。

---

## 9. 常见问题

**后端首次查询报 500，日志提到 tiktoken / o200k_base**

确认 `backend/data/tiktoken_cache` 存在且启动脚本已设置 `TIKTOKEN_CACHE_DIR`。本包已内置该词表。

**嵌入相关报错 401 / 403**

检查 `DASHSCOPE_API_KEY` 或 `EMBEDDING_API_KEY` 是否有效；只填 `DASHSCOPE_API_KEY` 时启动脚本会自动继承。

**前端聊天历史 503**

PostgreSQL 未启动，且 `CHAT_HISTORY_STORAGE_MODE=prisma`。启动 PostgreSQL、执行 `db:deploy`，或把模式改为 `auto` / `mock`。

**`pnpm: command not found` / Node 版本过低**

安装 Node.js 20.9+，再执行 `npm i -g pnpm@10.6.1`。

**端口被占用**

先执行 `.\start.ps1 -Stop`，或修改 `start.ps1` / `start.sh` 中的端口参数。

**登录页仍显示前端 Mock 登录**

确认 `.env.local` 中 `NEXT_PUBLIC_MIA_RAG_AUTH_URL` 指向 `http://127.0.0.1:6006`，并重启前端（`NEXT_PUBLIC_` 变量在构建时注入）。

---

## 10. 安全说明

- 仓库只提交 `.env.example`，真实密钥、上传文件、数据库均不提交。
- 部署到公网前，请替换 `JWT_SECRET_KEY`、`FEDERATION_INTERNAL_TOKEN`、`FEDERATION_SM4_KEY`，并启用 HTTPS。
- 默认管理员密码仅用于本地演示，首次登录后请修改。
- 节点间通信默认使用 SM4 加密；生产环境应限制 6006 / 6008 / 9000 端口的访问范围。

---

## 11. 团队协作

分支、提交与合并规范见 [docs/GIT_WORKFLOW.md](docs/GIT_WORKFLOW.md)。
