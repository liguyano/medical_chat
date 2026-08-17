# 前端与智能体后端联调开发计划

> 创建日期：2026-08-16
>
> 开发工作区：`D:\A-AICodeWork\medical-evaluate`
>
> 开发分支：`feat/frontend-api-integration`
>
> 基线提交：`35d8aab`
>
> 当前状态：进入真实 API 联调与后端缺陷同步修复阶段

## 1. 目标与实施原则

目标是在不破坏现有可用 Mock 原型的前提下，为前端增加真实后端接入能力，并在后端完成后实现任务、对话、监控、字段抽取、宣教、知情同意和护士反馈的完整联调。

实施原则：

- [X] 1.1 使用独立 worktree，避免影响主工作区正在开发的后端代码。
- [X] 1.2 保留 Mock 模式，后端不可用时仍可完整演示。
- [X] 1.3 通过环境变量切换 `mock`、`api`；语音固定使用 WebSocket。
- [X] 1.4 页面不直接调用 `fetch`、`EventSource` 或 WebSocket，统一通过 Repository 和传输适配层。
- [X] 1.5 所有后端数字ID在前端边界转换为字符串，避免 BigInt/JSON 精度和比较问题。
- [ ] 1.6 后端完成并合入 `main` 前，不将本分支合回 `main`。

## 2. 开发前必须确认的接口契约

### 2.1 任务状态

现有前端状态：

```text
pending
in_progress
pending_review
completed
cancelled
```

当前后端模型状态：

```text
pending
in_progress
completed
cancelled
```

- [ ] 2.1.1 后端增加 `pending_review`，或提供独立 `review_status` 字段。
- [ ] 2.1.2 明确知情同意完成后任务进入 `pending_review`，护士最终确认后才进入 `completed`。
- [ ] 2.1.3 明确会话 `paused`、`interrupted`、`error` 与任务状态之间的转换规则。

### 2.2 任务DTO

现有 `GET /api/tasks/{task_id}` 无法支撑任务详情和患者列表展示，至少需要以下内容：

- [ ] 2.2.1 患者姓名、住院号、科室、病区和床号。
- [ ] 2.2.2 参与人类型、参与人姓名和与患者关系。
- [ ] 2.2.3 评估场景、量表ID/名称/版本、计划开始时间和护士备注。
- [ ] 2.2.4 责任护士ID和姓名。
- [ ] 2.2.5 是否需要知情同意、宣教主题和人工介入状态。
- [ ] 2.2.6 当前阶段、字段进度、AI摘要和会话ID。

### 2.3 缺少的业务接口

- [ ] 2.3.1 在院患者列表、患者详情和住院记录接口。
- [ ] 2.3.2 量表目录、量表版本、分组、题目和选项接口。
- [ ] 2.3.3 传统问卷草稿保存、正式提交和读取接口。
- [ ] 2.3.4 人工介入请求、护士接管和处理完成接口。
- [ ] 2.3.5 护士复核草稿、退回重评和最终确认接口。
- [ ] 2.3.6 AI对话质量、AI评估质量评价接口。
- [ ] 2.3.7 宣教理解确认和未理解转人工接口。
- [ ] 2.3.8 知情同意条款级“已听完/已理解/不理解/拒绝”记录接口。

### 2.4 SSE事件协议

建议后端统一使用以下事件信封：

```json
{
  "event_id": "redis-stream-id",
  "event_type": "text_delta",
  "task_id": "1",
  "session_id": "session-1",
  "message_id": "message-1",
  "occurred_at": "2026-08-16T14:00:00Z",
  "payload": {}
}
```

建议事件类型：

```text
session_snapshot
session_status
user_transcript_delta
user_transcript_completed
assistant_message_started
assistant_text_delta
assistant_audio_delta
assistant_message_completed
extraction_updated
progress_updated
education_triggered
education_status_updated
consent_triggered
handoff_requested
handoff_resolved
task_status_updated
error
heartbeat
```

- [ ] 2.4.1 明确每种事件的 `payload` Schema。
- [ ] 2.4.2 SSE响应必须发送标准 `id:`，支持 `Last-Event-ID` 请求头或查询参数恢复。
- [ ] 2.4.3 明确事件幂等键，前端重连后不得重复追加消息和事件。
- [ ] 2.4.4 EventSource鉴权使用 HttpOnly Cookie；原生 EventSource不能添加自定义 Authorization Header。

### 2.5 语音传输

后端连接豆包使用 WebSocket，但浏览器到后端的设计尚未统一。

建议：

```text
文本输入：POST REST
文本/状态/字段/宣教事件：SSE
患者实时语音上行和AI音频下行：WebSocket
网络或设备不支持时：降级到文本输入
```

- [X] 2.5.1 确认浏览器语音采用 WebSocket。
- [ ] 2.5.2 明确浏览器发送 PCM16 16kHz 单声道还是 Opus。
- [ ] 2.5.3 如使用 PCM16，必须正确完成 Float32 到 Int16 的限幅和量化，不能直接转换底层字节。
- [ ] 2.5.4 明确开始录音、音频片段、提交、打断、暂停、恢复和关闭会话消息。
- [ ] 2.5.5 明确AI音频片段序号、采样率、编码格式和播放完成事件。

## 3. 前端基础设施

- [X] 3.1 增加运行时配置：
  - `NEXT_PUBLIC_DATA_MODE=mock|api`
  - `NEXT_PUBLIC_API_BASE_URL`
  - `NEXT_PUBLIC_DIALOG_TRANSPORT=sse|websocket`
- [X] 3.2 实现统一 HTTP Client：超时、错误解析、Cookie、取消请求和可观察错误。
- [X] 3.3 建立 `api-contracts` DTO和前端领域模型转换器。
- [X] 3.4 建立 Repository 接口及 Mock/API 两套实现。
- [X] 3.5 增加请求状态：`idle/loading/success/error`，不再用静默本地修改伪装后端成功。
- [X] 3.6 保留本地草稿，API模式进行600ms防抖云端保存；服务端冲突策略待后端返回版本字段后补充。

## 4. 任务、患者和传统问卷接入

- [X] 4.1 患者列表和住院记录已提供 API 适配；患者详情契约待后端确认。
- [X] 4.2 量表目录已提供 API 适配，Mock 题库继续作为后端未完成时的原型来源。
- [X] 4.3 任务创建已接入双适配；列表、详情继续兼容现有 Store，取消接口待后端联调。
- [X] 4.4 创建任务后使用后端返回的 `task_id`、`task_no` 和 `session_id`。
- [X] 4.5 传统问卷答题使用本地即时草稿和后端防抖保存。
- [X] 4.6 正式提交后锁定患者答案并进入待复核状态。
- [X] 4.7 API失败时展示错误并保留现有数据。

## 5. 患者AI对话接入

- [X] 5.1 API模式页面加载时先获取会话快照、历史消息和字段。
- [X] 5.2 建立患者会话SSE，支持指数退避、查询参数 Last-Event-ID 和事件幂等。
- [X] 5.3 API模式文本输入改为REST提交，正式回复统一由SSE接收。
- [X] 5.4 按 `message_id` 合并文本增量，完成事件到达后结束流式状态。
- [X] 5.5 消费字段抽取、进度、宣教、知情同意和人工介入事件。
- [X] 5.6 保留 Mock 对话脚本作为无后端演示模式。
- [X] 5.7 实现患者暂停、继续、找护士、语音打断能力和文本降级。

## 6. 实时语音

- [X] 6.1 封装麦克风权限和设备异常状态。
- [X] 6.2 原型使用浏览器音频处理节点输出固定音频帧；生产优化可切换 AudioWorklet。
- [X] 6.3 实现 PCM16 16kHz 单声道限幅、降采样和量化。
- [X] 6.4 建立语音 WebSocket 生命周期；协议级重连策略待后端关闭码确认。
- [X] 6.5 实现AI音频播放队列、清空和实时打断；片段序号校验待后端事件落地。
- [X] 6.6 启用回声消除、降噪和自动增益，并显示聆听、转录、思考、播报状态。
- [X] 6.7 权限拒绝、设备缺失、网络中断或模型失败时自动切换文本模式。

## 7. 护士监控、复核与质量评价

- [X] 7.1 建立护士多会话监控SSE。
- [X] 7.2 按任务/会话分发消息、字段、风险、宣教和状态事件。
- [ ] 7.3 接入对话历史分页和证据定位。
- [X] 7.4 接入逐轮点赞、点踩和备注。
- [X] 7.5 接入人工介入接管和事件处理。
- [X] 7.6 接入护士复核、修改原因、退回和最终确认。
- [X] 7.7 接入AI对话质量和AI评估质量评价。

## 8. 知情同意

- [ ] 8.1 接入后端触发的知情同意事件和文档内容。
- [X] 8.2 逐条保存播放、理解、不理解和人工解释状态；拒绝流程待后端契约确认。
- [X] 8.3 Canvas签名导出PNG Data URL并调用签名接口。
- [X] 8.4 提交前校验参与人、强制条款和总体决定；文档版本字段待后端返回。
- [X] 8.5 UI明确标注当前签名仅为原型演示。

## 9. 测试与验收

- [X] 9.1 DTO和领域模型映射单元测试。
- [X] 9.2 HTTP成功与错误解析测试；超时和取消的浏览器集成测试待真实联调。
- [X] 9.3 SSE事件信封解析和兼容结构测试；真实断线重连待后端联调。
- [X] 9.4 PCM16编码和降采样测试；播放队列和打断状态机测试待补充。
- [X] 9.5 Mock模式回归测试，确保原型仍可独立运行。
- [ ] 9.6 API模式使用后端测试环境完成任务、对话、监控、复核和签名闭环。
- [X] 9.7 执行 `pnpm test`、`pnpm lint`、`pnpm typecheck` 和 `pnpm build`。
- [X] 9.8 使用真实浏览器验证桌面端、390px手机端和控制台；真实麦克风权限需后端 WebSocket 可用后验证。

## 10. 后端完成后的合并流程

- [ ] 10.1 后端开发者将代码和迁移提交到本地 `main`，确保主工作区无未提交文件。
- [ ] 10.2 在本 worktree 中合并最新 `main`。
- [ ] 10.3 根据实际 OpenAPI 和事件协议修正前端 DTO与适配器。
- [ ] 10.4 启动后端必要依赖并执行真实联调测试。
- [ ] 10.5 更新开发进度、测试指南和审查记录。
- [ ] 10.6 测试通过后将 `feat/frontend-backend-integration` 合并回本地 `main`。
- [ ] 10.7 工作区干净且本地 `main` 状态正确后，再推送远程 `main`。

## 11. 2026-08-17 真实 API 闭环实施

本轮以 `backend/docs/API.md` 为前端对接入口，同时以实际 FastAPI 路由、数据库设计和
第一期文本闭环约束校正文档漂移。范围仅包含患者、量表、AI 对话任务、文本问诊、
字段抽取和护士单会话实时监控；语音、传统问卷、知情同意、宣教、人工介入、评分和
护士复核不在第一期真实 API 范围内。

### 11.1 契约统一

- [X] 11.1.1 REST 成功响应统一使用 `{code,message,data}`，HTTP Client 负责校验
  `code` 并返回 `data`。
- [X] 11.1.2 对齐患者、量表、任务、会话、历史和抽取 DTO，数字 ID 在映射边界转字符串。
- [X] 11.1.3 对齐 `ai_dialogue`、任务编号、会话编号和消息发送路径。
- [X] 11.1.4 SSE 使用患者端 `/api/sse/dialog/{session_no}` 与护士端
  `/api/sse/monitor/{session_no}`，支持 `Last-Event-ID`。

### 11.2 前端完整对接

- [X] 11.2.1 任务创建页只使用后端患者和已发布量表，不在 API 失败时静默回退 Mock。
- [X] 11.2.2 发布 AI 对话任务后保存后端 `task_no/session_no`，患者端可直接进入问诊。
- [X] 11.2.3 患者对话页加载历史与抽取快照、订阅 SSE、发送患者答案并展示 AI 下一问。
- [X] 11.2.4 护士监控页按会话订阅 SSE，实时展示问答、字段、约束和完成状态。
- [X] 11.2.5 API 模式隐藏或禁用第一期未实现的操作，避免调用不存在的后端端点。
- [X] 11.2.6 页面保留 Mock 模式，但 API 模式不得混入 Mock 数据。

### 11.3 后端联调修复

- [X] 11.3.1 修复任务创建 ORM 字段、采集模式枚举和统一响应包装。
- [X] 11.3.2 创建任务时原子生成 `care_task`、`interaction_session` 和每量表
  `assessment_instance`，提交后派发四个 Worker。
- [X] 11.3.3 修复 AI 先问、患者同轮回答、DB 历史恢复和 Redis 状态恢复。
- [X] 11.3.4 修复多量表 Extraction 写库、抽取事件和会话完成状态。
- [X] 11.3.5 修正 SSE 信封、事件名、首问重放和护士监听路径。
- [X] 11.3.6 更新 `backend/docs/API.md`，确保文档与实际代码一致。

### 11.4 验证与交付

- [X] 11.4.1 运行后端静态检查与现有测试。
- [X] 11.4.2 运行前端单元测试、lint、typecheck 和 build。
- [X] 11.4.3 使用真实浏览器验证桌面端和 390px 手机端关键流程及控制台。
- [X] 11.4.4 完成代码审查、修复发现的问题并提交。
