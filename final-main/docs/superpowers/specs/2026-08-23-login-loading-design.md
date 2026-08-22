# 登录成功 Loading 动效设计

## 目标

登录成功后不立即进入宏观平台。登录窗口先完成内容淡出、蓝色色块扩张和四线离屏动画，最终停留在覆盖整个 SVG viewBox 的纯蓝状态，为后续主页面转场提供稳定起点。

## 设计

- 主责文件：`apps/main-platform/app/windows/login/LoginIntroWindow.tsx`
- 协同文件：`apps/main-platform/app/login-window-demo.tsx`、`apps/main-platform/app/windows/shared/coords.ts`
- `LoginForm` 的成功回调契约不变；`LoginIntroWindow` 包装该回调，先让父层写入认证身份，再启动 loading 时间线。
- 父层不再在认证成功回调中调用 `setActiveWindow("macro")`，宏观窗口在 loading 阶段不挂载。
- 主扩张段使用 `FULLSCREEN_COORDS`、`1.02s` 和 `power3.inOut`，四线、clip、色块和布局继续由同一个 `Coords` 投影。
- 主扩张完成后使用 `getLineExitCoords(FULLSCREEN_COORDS)` 播放约 `0.14s` 的线条离屏尾段；色块和 clip 保持全屏。
- 表单、介绍文案、提示层和 Logo 使用 `autoAlpha` 同步淡出；蓝色色块保持 `BRAND_BLUE`。
- loading 阶段按需求忽略 `prefers-reduced-motion`，现有 intro 阶段的减弱动效策略保持不变。

## 不变内容

- 不修改认证接口、登录失败提示、注册申请流程或 `LoginForm` 成功回调签名。
- 不新增独立遮罩层、动画库或宏观窗口内部逻辑。
- 组件卸载时继续清理 GSAP timeline、ticker、事件监听器和 loading 触发 ref。

## 验收标准

1. 登录失败时仍停留在登录表单并显示原有错误。
2. 登录成功后身份立即写入，但宏观窗口不挂载。
3. 表单、文案、提示和 Logo 淡出，蓝色色块扩张到完整 SVG viewBox。
4. 色块到达视口边界后，四条线继续向各自方向离屏。
5. 最终页面保持纯蓝，重复点击不会重播 loading。
6. 退出并重新进入登录窗口时，intro 能从初始状态重新播放。

## 扩展性审查

登录窗口继续拥有登录阶段的视觉状态机，父层只维护认证和窗口选择。全屏与离屏几何集中在共享坐标模块，后续新增 loading 后续阶段可以从稳定终态接入，不需要复制 SVG 边界计算。尾段的几何分离和完整动效偏好均记录为显式边界，避免未来维护者误认为是遗漏。
