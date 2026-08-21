# 模块索引

## 主应用

`apps/main-platform` 是当前唯一的用户界面应用，使用 Next.js App Router。

- `app/page.tsx`：应用入口，只挂载 `LoginWindowDemo`。
- `app/login-window-demo.tsx`：窗口状态源，负责登录、宏观、数据库和主对话窗口的切换。
- `app/windows/**`：四个既有窗口的 UI、动效和交互。
- `app/styles/**`：窗口语言的主样式来源；Tailwind 仅保留配置兼容。
- `app/api/**`：浏览器调用的 Route Handlers，负责统一接口契约与外部服务降级。

## 本地演示服务层

- `app/lib/client/auth-adapter.ts`：真实认证地址已配置时转发认证；未配置时启用内置演示账号。
- `app/lib/server/chat-history/**`：默认使用 mock 聊天历史，避免前端演示依赖 Prisma 或数据库。
- `app/lib/server/node-data/**` 与 `app/lib/database-store.ts`：聚类、文件、指标和检索的 JSON store 服务层。
- `app/lib/server/offline-demo.ts`：集中定义无后端地址时的存储和服务降级策略。
- `app/lib/server/federation/**`：联邦问答与中心节点健康检查；无中心地址时返回稳定演示数据。

## 可选真实服务

以下环境变量存在时，对应 Route Handler 会保留真实服务路径：

- `NEXT_PUBLIC_MIA_RAG_AUTH_URL`
- `MIA_RAG_NODE_URL`
- `FEDERATION_CENTRAL_BASE_URL`

未配置时，应用必须仍可完成登录、窗口导航、聚类管理、对话保存和检索演示。
