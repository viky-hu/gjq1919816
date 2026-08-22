# 登录首屏动画首帧优化设计

## 目标

消除登录首屏从打开到 hydration 完成之间的错误静态帧。页面首次可见时保持纯白背景，不展示已经处于最终状态的 SVG 线条、色块或文字；客户端接管后从明确的动画起始态开始播放既有入场时间轴。

## 根因

`LoginIntroWindow` 的 SVG 由 Next.js 预渲染为完整可见状态，线条 dash、面板尺寸和文字透明度要等客户端 `useLayoutEffect` 执行后才被 GSAP 重置。于是首帧会短暂显示最终图案，随后被重置并重新播放。首屏同时初始化 Three.js WebGL 背景和 SVG 路径测量，会放大客户端接管前后的感知停顿。

## 设计

- 主责文件：`apps/main-platform/app/windows/login/LoginIntroWindow.tsx`
- 协同文件：`apps/main-platform/app/styles/window-1-login.css`、`apps/main-platform/app/beams-background.tsx`
- 在 SSR 输出层直接声明动画起始态，避免依赖客户端首次 `gsap.set()` 才隐藏元素。
- 为 SVG 线条和 logo 路径使用归一化 `pathLength`/dash 起始值，减少首屏同步测量和写入。
- 将 GSAP 初始化收敛到带 scope 和清理的 React 集成方式，保留现有两阶段时间轴和交互契约。
- 首屏保持纯白；在动画初始化完成前，SVG 通过明确的 ready 状态保持不可见，避免显示错误中间态。
- Three.js 光束背景不阻塞 SVG 主动画启动；在主视觉开始后再初始化或以独立的低优先级路径启动，并继续保留卸载清理。
- 使用 `gsap.matchMedia()` 支持 `prefers-reduced-motion: reduce`：跳过复杂入场，直接显示可用的稳定引导状态。

## 不变内容

- 不改变登录/注册表单业务逻辑和阶段切换逻辑。
- 不改变现有线条、色块、logo、文字的最终视觉布局和时间轴顺序，除非为消除首帧闪现所必需。
- 不引入新的动画库或页面级 loading 组件。

## 验收标准

1. 首次加载时不会出现完整静态 SVG 先显示、随后消失再播放的闪烁。
2. 首屏在客户端动画接管前保持纯白，不显示错位文字或可交互的隐藏表单。
3. SVG 入场动画仍按现有顺序播放，点击/滚轮进入登录阶段的行为不回归。
4. Three.js 背景初始化不会阻塞关键 SVG 入场动画。
5. `prefers-reduced-motion: reduce` 下不播放复杂入场，同时页面内容可直接使用。
6. 动画组件卸载和重新挂载时不存在残留 tween、事件监听器或 WebGL 渲染循环。

## 扩展性审查

首帧状态由 SVG 标记/CSS 与 GSAP 共同定义，避免未来新增元素时再次依赖“客户端先显示、再隐藏”的隐式顺序。动画主时间轴、背景渲染和可访问性策略保持分层，后续新增背景效果或 reduced-motion 分支不需要修改登录表单内部逻辑。
