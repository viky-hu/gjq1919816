# MiA-RAG 本地一键启动设计

## 目标

双击项目根目录的 `一键启动.bat` 后，同时启动本地 FastAPI、节点服务和 Next.js 开发前端，并在缺少必要配置时给出明确的填写位置。

## 方案

- BAT 只负责定位项目根目录、调用 PowerShell 启动器，并在失败时保留窗口供用户查看。
- PowerShell 启动器负责检查 Python、pnpm、前端依赖和后端依赖，加载根目录的 `backend.local.env`，生成本地前端 `.env.local`，再分别打开三个服务窗口。
- 服务端口固定为 FastAPI `6006`、节点服务 `6008`、前端 `3000`。已经占用的端口不重复启动。
- 默认使用开发联调模式，启动完成后打开 `http://127.0.0.1:3000`。
- API Key 和本机模型路径只放在被 Git 忽略的 `backend.local.env` 中；BAT 不把密钥写入脚本。

## 配置提示

启动器在根目录找不到 `backend.local.env` 时创建/提示使用 `backend.local.env.example`。需要用户填写的主要变量是：

- `DEEPSEEK_API_KEY`：DashScope/Qwen 兼容接口的 API Key，用于摘要和回答生成。
- `MODEL_PATH`：MiA-EMB 模型目录或模型仓库 ID。
- `BASE_MODEL_PATH`：Qwen3-Embedding-8B 基础模型目录或模型仓库 ID。

本地联调的 `FEDERATION_INTERNAL_TOKEN`、`JWT_SECRET_KEY` 和 `FEDERATION_SM4_KEY` 使用脚本内的开发默认值，也允许在 `backend.local.env` 覆盖。

## 验证

验证启动器能从任意当前目录定位项目；能发现 Python/pnpm 缺失并给出提示；能加载 `backend.local.env`；能生成正确的前端后端地址；能启动三个服务窗口并自动打开前端；已有端口被占用时不会重复启动。
