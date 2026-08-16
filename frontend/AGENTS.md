<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# 前端模块说明

## 当前原型架构

- 使用 Next.js App Router，医护端路由位于 `src/app/nurse`，患者端路由位于 `src/app/patient`。
- `src/lib/stores/useUserStore.ts` 管理演示登录身份。
- `src/lib/stores/useTaskStore.ts` 管理任务、传统问卷草稿、知情同意、护士复核和质量评价，并通过 Zustand persist 保存到浏览器。
- `src/lib/stores/useChatStore.ts` 管理 AI 会话、结构化答案、风险/宣教事件和逐轮反馈，并通过 Zustand persist 保存到浏览器。
- `src/lib/mock` 是原型题库、量表、患者、任务和对话演示数据的唯一来源；新增量表题目时必须同步任务量表与题目分组映射。
- 原型中的 AI 流式输出、语音、二维码、人脸识别和条款播报均为前端模拟，不得描述为真实生产能力。

## 常用检查命令

在 `frontend` 目录执行：

```powershell
pnpm lint
pnpm typecheck
pnpm build
pnpm check
```

涉及页面交互的修改还需使用真实浏览器验证桌面端和 390px 手机视图，并检查浏览器控制台无错误。
