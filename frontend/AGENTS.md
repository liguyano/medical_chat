<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

# 前端模块说明

## 当前原型架构

- 使用 Next.js App Router，医护端路由位于 `src/app/nurse`，患者端路由位于 `src/app/patient`。
- 患者端新版 UI 以 390px 移动视口为主要验收基准；普通页面由
  `src/components/layout/PatientLayout.tsx` 提供最大 430px 的居中移动画布。AI 对话页在
  1024px 以上允许通过 `desktopAside` 使用双栏布局，左栏消费 Extraction 字段快照并分为
  “已记录 / 已问未记录 / 还没问”：只有 `recorded=true` 的题显示最终值，`asked` 只用于
  展示询问状态，不得把候选题、冷却状态或问句题号关联伪装成结构化答案。
  患者端设计令牌统一放在 `src/app/globals.css` 的 `.patient-app` 作用域，禁止用患者端变量覆盖医护端。
- 患者端交付素材复制到 `public/assets/patient`，页面不得直接引用 `docs/ui` 原型截图；
  通用图标、状态、语音 Orb、聊天气泡和呼叫护士入口位于 `src/components/patient`。
- 患者端 UI 重构只能消费现有 Repository、Store、SSE 和语音 WebSocket 状态；原型有展示但
  后端尚未返回的状态必须保留明确前端展示与对接位置，并在 `docs/review` 记录，禁止为了视觉
  复现修改接口路径、DTO 或传输协议。
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
- SSE 信封必须区分领域 `event_id` 与传输 `stream_id`：业务卡片和提交接口使用
  `event_id`，断线续读和传输去重使用 `stream_id`。API 模式加载数据库事件快照前必须
  清除当前任务在 `sessionStorage` 中残留的旧领域卡片，再以快照重建。
- `education_triggered` 必须渲染医学宣教原文卡片并按 `spoken_content` 自动播报；
  患者确认阅读后通过仓储调用后端持久化 `education_status_updated`，医护回放显示确认状态和时间；
  `consent_triggered` 必须在对话内渲染强制条款、播放和签名组件；`handoff_requested`
  必须同时更新患者呼叫状态和医护端全局提醒。页面刷新时通过对话事件快照接口恢复组件，
  不能只依赖当次 SSE。
- 医护端登录后通过 `/api/sse/nurse/alerts` 订阅责任护士全局提醒流，任意医护页面均应
  显示患者姓名、床位、呼叫原因和请求的人工操作。
- 患者主动呼叫与 AI 工具呼叫必须使用不同的来源标识和视觉卡片；呼叫历史、工具结果、
  处理状态及护士工号/姓名/时间必须从会话事件快照恢复。医护监控的对话回放应把普通消息、
  宣教/知情同意工具结果和呼叫工具结果按时间合并展示，不能只渲染 `interaction_message`。
- 患者发言次数不是评估进度。`answeredQuestionCount` 与任务进度只能由后端快照或
  `progress_updated`（必填、非派生结构化答案进度）更新。
- AI 会话 `pending` 表示 Schedule Task-todo 与首问正在后台准备；该阶段患者输入保持禁用，
  首问完成并转为 `active` 后才允许发送。
- API 模式进入患者对话页时必须以最新后端快照校正 Zustand 中的持久化会话，不能因为
  sessionStorage 已存在旧会话就跳过刷新；首问完成事件必须把旧 `pending` 状态切换为
  `active`。`streamingTaskId` 等瞬时传输状态不得跨页面恢复为正在生成。
- 患者实时语音仅通过 `src/lib/transports/voiceSocket.ts` 连接后端 WebSocket；浏览器音频必须量化为 16kHz 单声道 PCM16，不得直接发送 Float32 底层字节。
- 语音或网络失败时保留文字输入，并在 UI 显示 Mock/API、SSE 和语音连接状态。
- API 模式语音页面使用 Qwen Realtime 的后端网关；患者/AI 音频完成索引通过
  `applyRealtimeEvent.ts` 绑定到 `InteractionMessage.audioUrl`，统一由 `ChatBubble`
  的受保护 WAV 播放控件回放，医护监控页与患者页共享该事件适配逻辑。
- 语音评估收到 `task_status_updated` 后，患者端必须先等待当前 PCM 播放队列排空，
  且收到 Voice Gateway 的 `response_completed` 控制标记，再关闭麦克风和 WebSocket、
  显示完成提示并移除输入控件；`response.done` 不等于浏览器已播报完成。语音模式必须
  提供独立“关闭语音”按钮，主动关闭后保留文字输入能力。
- 前端单元测试位于 `frontend/tests/`，使用 Vitest；涉及适配器变更时至少覆盖 DTO 映射、事件解析和传输边界。
- 护士监控页的逐条 AI 质评通过 `CareRepository` 调用 `/api/rating`，整体质量评价通过 `/api/quality-reviews`；Mock 模式继续使用 Zustand sessionStorage，不得把本地保存描述为后端已入库。
- 结构化答案的 `selectedOptions` 是内部选项编码，只用于审计；患者端和医护端必须通过 `displayValue` / `selectedOptionLabels` 展示目标量表真实值，禁止把 `option_3` 等编码直接暴露给用户。
- API 模式进入医护监控详情页时必须刷新最新任务详情，使用后端住院号、床位、科室、性别年龄、入院时间和在院状态构造顶部患者摘要，不能复用 sessionStorage 中的旧任务快照。
- API 模式医护登录成功后必须调用 `CareRepository.listMyTasks()` 刷新当前护士负责的历史任务，并替换 `useTaskStore` 中的本地快照；监控中心、任务管理和工作台不得仅依赖 sessionStorage。
- API 模式患者登录及患者任务页刷新必须调用
  `CareRepository.listPatientTasks()` → `/api/patients/me/tasks`，只依赖患者 HttpOnly
  Cookie；患者端禁止调用医护专用 `/api/tasks`，也不得依赖旧浏览器的医护登录缓存。
- AI 对话任务创建后，患者端只会收到后端已完成首问准备并设置可见时间的任务；医护端任务详情
  轮询 `getTask()` 展示 `Schedule prepare`、`Dialog preheat`、`Dialog opening` 三阶段状态和
  输出。准备失败时显示错误与重试按钮，调用 `CareRepository.retryTaskPreparation()`，不能在
  前端自行把失败任务标记为可用。
- `/nurse/config` 通过 `CareRepository` 管理宣教材料、拦截特征字典和评估量表：
  宣教与规则使用结构化表单，量表使用完整 JSON 查看和编辑。API 与 Mock 模式必须保持
  同一接口，页面须等待医护身份就绪后再加载配置，保存后直接生效。
- 传统问卷任务在 API 模式通过 `CareRepository.getQuestionnaire()` 加载本次任务绑定的
  真实量表题目、分组、选项和服务端草稿；草稿与正式提交分别调用
  `PUT /api/tasks/{task_ref}/questionnaire/draft` 和
  `POST /api/tasks/{task_ref}/questionnaire/submit`。页面必须以服务端题目/提交状态为准，
  正式提交后只读，退回后允许继续填写，不能用 `prototypeQuestions` 补齐 API 数据。
- 传统问卷患者进度只统计必填且非派生题；派生题只读展示。医护复核页展示患者答案真实标签、
  计分和风险解释，不渲染 AI 证据或虚构的人机差异。API 与 Mock Repository 保持同一问卷
  接口，后端返回的选项编码仅用于请求和审计，用户界面优先展示标签/值。
- `/nurse/tasks/[id]/nursing-plan` 通过 `CareRepository` 查询和生成患者画像与护理计划，
  支持摘要编辑、计划项接受/修改/拒绝、护士备注和最终确认；API 与 Mock 模式保持同一
  闭环。真实模型生成接口单独使用 120 秒超时，避免普通请求超时提前中断结果展示。
- `/nurse/patients`、`/nurse/patients/new`、`/nurse/patients/[patientId]` 和编辑页统一通过
  `CareRepository` 管理患者主档与本次住院记录；列表需展示护理级别、过敏摘要、任务摘要
  和人工介入状态，新增/编辑共享同一表单，API 模式禁止读取 `src/lib/mock` 补数据。
- 患者主动呼叫必须为一次按钮异步操作生成唯一 `clientInvocationId` 并在请求完成前锁定
  重复提交；HTTP 回退、SSE 与历史快照继续按领域 `event_id` / `request_id` 更新同一组件。
  不同领域事件必须分别展示，前端不得按工具名称或参数合并模型调用。

## 生产部署访问约定

- 生产前端由宝塔 Nginx 以 HTTPS 域名提供服务，API、SSE 和 WebSocket 必须使用
  当前站点同源路径：`/api`、`/api/sse/*`、`/api/ws/*`。
- 禁止在页面、仓储、传输层或生产环境变量中写死 `http://localhost:8000`、
  `127.0.0.1:8000` 或 Docker 内部服务名。开发 Mock/API 联调可以使用本地地址，
  但生产构建必须使用 `PUBLIC_ORIGIN` 对应的 HTTPS 域名。
- 修改 `src/lib/api`、`src/lib/transports` 或运行时地址解析时，必须同时验证
  医护端和患者端的 Cookie、SSE 断线续读、WebSocket 语音连接以及音频相对地址。
- `frontend/next.config.ts` 必须保持 `output: 'standalone'`，以供生产镜像运行；
  修改输出模式时必须同步更新 `deploy/frontend.Dockerfile`。
- 宝塔代理规则的事实来源是 `deploy/baota-reverse-proxy.conf`，不得新增需要
  直接暴露后端端口的前端路由。
- 生产前端通过 `deploy/build-images.ps1` 构建为目标 Linux 平台镜像；构建时必须
  传入最终 HTTPS `PublicOrigin`，服务器不得重新执行 Next.js 构建。
- 真实演示数据由后端 PostgreSQL 与 `backend/storage` 恢复，前端不得新增本地
  患者资料、对话、签名或音频副本，也不得把真实数据包提交 Git 或放入静态资源目录。
- 生产浏览器只访问宝塔 Nginx 提供的 HTTPS 同源地址；前端页面不能提供“浏览器
  一键执行 Docker/恢复脚本”的逻辑，部署动作必须由服务器终端执行。

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
