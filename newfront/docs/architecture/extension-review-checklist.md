# 扩展性审查清单

## 本次基线复刻

- [x] 窗口状态仍由 `LoginWindowDemo` 统一维护，未新增第二个顶层窗口状态源。
- [x] 离线认证、聊天历史、节点数据和联邦降级分别落在 `lib` 与 `app/api`，窗口组件不直接聚合后端逻辑。
- [x] 数据库聚类的新增、重命名、删除和恢复复用 JSON store 服务层，未在多个窗口复制数据逻辑。
- [x] 真实后端入口仍通过环境变量保留，演示模式不改变浏览器侧 API 路径。
- [x] v1 默认路径不再要求 Prisma Client、PostgreSQL 或生产环境变量。

## 后续新增前检查

- 新窗口是否通过 `LoginWindowDemo` 的 `ActiveWindow` 契约接入。
- 新节点或模型能力是否优先扩展服务层与 Route Handler，而不是写入窗口组件。
- 新的远程依赖在无地址、离线或失败时是否有稳定的可见降级状态。
- 共享逻辑是否已放入 `app/windows/shared/**` 或 `app/lib/**`，避免跨窗口复制。
- 是否保持现有 CSS、GSAP、SVG/Canvas/Three 与 lucide-react 的视觉和实现语言。
