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
- 用户、任务和对话 Store 使用 `sessionStorage`，允许医护端与患者端在不同标签页同时联调，避免角色登录态和任务状态互相覆盖。
- `src/lib/mock` 是原型题库、量表、患者、任务和对话演示数据的唯一来源；新增量表题目时必须同步任务量表与题目分组映射。
- 原型中的 AI 流式输出、语音、二维码、人脸识别和条款播报均为前端模拟，不得描述为真实生产能力。

## 后端联调适配架构

- `src/lib/runtime/config.ts` 统一读取 `NEXT_PUBLIC_DATA_MODE`、API 地址和请求超时；默认必须保持 `mock`，确保后端未启动时原型仍可演示。
- 页面不得直接调用后端传输 API。普通命令统一通过 `src/lib/repositories`，其中 `MockCareRepository` 与 `ApiCareRepository` 实现相同接口。
- 医护登录同样通过 `CareRepository`：Mock 模式校验本地演示账号，API 模式调用
  `/api/auth/staff/login` 并使用独立 HttpOnly Cookie；退出时同步调用后端清理会话。
- `src/lib/api` 保存后端 DTO、HTTP Client 和领域模型映射。后端数字 ID 必须在映射边界转换为字符串。
- 患者和护士的文本、任务状态、字段抽取、宣教与人工介入事件通过 `src/lib/transports/sseClient.ts` 接收，并由 `applyRealtimeEvent.ts` 幂等写入 Zustand Store。
- `education_triggered` 必须渲染医学宣教原文卡片并按 `spoken_content` 自动播报；
  `consent_triggered` 必须在对话内渲染强制条款、播放和签名组件；`handoff_requested`
  必须同时更新患者呼叫状态和医护端全局提醒。页面刷新时通过对话事件快照接口恢复组件，
  不能只依赖当次 SSE。
- 医护端登录后通过 `/api/sse/nurse/alerts` 订阅责任护士全局提醒流，任意医护页面均应
  显示患者姓名、床位、呼叫原因和请求的人工操作。
- 患者发言次数不是评估进度。`answeredQuestionCount` 与任务进度只能由后端快照或
  `progress_updated`（必填、非派生结构化答案进度）更新。
- AI 会话 `pending` 表示 Schedule Task-todo 与首问正在后台准备；该阶段患者输入保持禁用，
  首问完成并转为 `active` 后才允许发送。
- 患者实时语音仅通过 `src/lib/transports/voiceSocket.ts` 连接后端 WebSocket；浏览器音频必须量化为 16kHz 单声道 PCM16，不得直接发送 Float32 底层字节。
- 语音或网络失败时保留文字输入，并在 UI 显示 Mock/API、SSE 和语音连接状态。
- 前端单元测试位于 `frontend/tests/`，使用 Vitest；涉及适配器变更时至少覆盖 DTO 映射、事件解析和传输边界。
- 护士监控页的逐条 AI 质评通过 `CareRepository` 调用 `/api/rating`，整体质量评价通过 `/api/quality-reviews`；Mock 模式继续使用 Zustand sessionStorage，不得把本地保存描述为后端已入库。

## 常用检查命令

在 `frontend` 目录执行：

```powershell
pnpm lint
pnpm typecheck
pnpm build
pnpm check
```

## 本地服务与生产构建

- `pnpm dev` 使用 Next.js 16 的 `.next/dev` 开发输出。
- `pnpm build` 生成 `.next` 生产输出，`pnpm start` 只运行已经生成的生产构建。
- 禁止在旧的 `pnpm start` 仍运行时重新执行 `pnpm build` 后继续复用旧进程；
  构建前必须停止生产服务，构建完成后重新启动，否则旧清单可能引用已被新构建
  替换的 chunk，导致 `ChunkLoadError`。
- 开发服务与生产服务不得同时占用 3000 端口。排查页面异常时必须记录
  `next start` 进程启动时间和 `.next/BUILD_ID` 写入时间，生产进程应晚于构建完成时间。

涉及页面交互的修改还需使用真实浏览器验证桌面端和 390px 手机视图，并检查浏览器控制台无错误。
