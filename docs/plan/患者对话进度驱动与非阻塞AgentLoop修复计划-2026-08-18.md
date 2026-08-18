# 患者对话进度驱动与非阻塞 AgentLoop 修复计划

## 1. 需求边界与架构决策

- [X] 1.1 问题 1（SSE 不流式）已通过清理历史 Worker 解决，本次不修改 SSE 主链路。
- [X] 1.2 问题 3（重复提问）重启后未复现，本次只保留幂等回归测试，不扩大修改范围。
- [X] 1.3 问题 2 的唯一完成条件确定为：全部生效量表的必填、非派生问题均已形成有效结构化答案。
- [X] 1.4 Dialog Agent 不等待 Schedule Agent 或 Extraction Agent；后台失败、重试或超时不得阻塞患者可见回复。
- [X] 1.5 Schedule Agent 在任务创建阶段生成并持久化 Task-todo，Dialog Agent 只消费该计划，不直接把数据库量表字段列表当作对话顺序。
- [X] 1.6 Schedule Agent 采用“逻辑会话绑定”：Task-todo、进度和最新引导写入 Redis/PostgreSQL，Worker 重启后可恢复；不依赖不可恢复的进程内 Python 实例。
- [X] 1.7 CICARE 六步规则作为会话阶段与提示词约束落地，但不要求每一轮机械重复完整六步话术。

## 2. 测试先行

- [X] 2.1 增加任务创建阶段 Schedule Agent 生成 Task-todo 的失败测试。
- [X] 2.2 增加 Dialog Agent 从 Task-todo 读取下一问、跳过已完成问题的失败测试。
- [X] 2.3 增加患者消息派发 Dialog 与后台 Agent 相互独立的失败测试。
- [X] 2.4 增加 Extraction 失败时 Dialog 仍可生成回复的失败测试。
- [X] 2.5 增加全部必填答案完成后由进度服务提交任务的失败测试。
- [X] 2.6 增加未完成、无效回答和患者反问不得触发完成的失败测试。
- [X] 2.7 增加 CICARE、自然过渡、回应患者问题、避免机械量表复述的提示词测试。
- [X] 2.8 增加前端仅使用后端结构化进度、不按患者消息轮数推进的失败测试。

## 3. Schedule Agent Task-todo

- [X] 3.1 定义可恢复的 Task-todo 数据结构，包含问题 ID、问题编码、所属量表、优先级、依赖、完成状态和患者友好表达。
- [X] 3.2 任务创建后先派发 Schedule prepare 任务，加载患者信息、量表配置、历史和工具上下文。
- [X] 3.3 Schedule prepare 生成 Task-todo 并持久化，成功后再派发 Dialog 首问预热。
- [X] 3.4 Dialog 首问从 Task-todo 获取，生成完成后任务进入患者可对话状态。
- [X] 3.5 每轮后台 Schedule observe 根据完整对话历史和结构化进度更新引导提示，但不得成为 Dialog 的前置依赖。
- [X] 3.6 Schedule 失败时保留上一次有效 Task-todo；没有可用计划时使用确定性量表计划降级并发布后台错误。

## 4. 非阻塞对话编排

- [X] 4.1 患者答案落库后立即独立派发 Dialog 任务。
- [X] 4.2 Schedule observe 与 Extraction 作为后台任务独立派发、独立重试，禁止使用会阻塞 Dialog 的 chain/group 前置关系。
- [X] 4.3 Dialog 读取“最后一个已成功发布的 Schedule 引导”，读取不到时继续按 Task-todo 对话。
- [X] 4.4 Dialog 根据当前问句、患者输入和已有进度决定自然回应、追问或选择下一题，不因后台状态缺失而等待。
- [X] 4.5 对后台超时、抽取失败和调度失败分别发布可观测事件，不把内部错误直接暴露给患者。

## 5. 进度驱动完成

- [X] 5.1 建立统一评估进度服务，按 AssessmentAnswer 统计必填、非派生问题。
- [X] 5.2 Extraction 成功写入答案后更新每个 submission、instance 和任务总进度。
- [X] 5.3 只有总进度完整且答案通过基础有效性校验时，才完成 session、task 和 assessment instance。
- [X] 5.4 Dialog Agent 删除基于问题数组下标和固定轮数的完成逻辑。
- [X] 5.5 未完成时患者可以继续提问；无效回答、澄清、反问不计入结构化评估进度。
- [X] 5.6 跨量表相同 question_code 共享已知事实，避免身高、体重等信息重复询问，同时分别落入对应量表答案。
- [X] 5.7 发布明确的 progress_updated 和 task_status_updated 事件。

## 6. CICARE 与自然对话

- [X] 6.1 Connect：核实患者身份、使用合适称呼并表达关心，仅在会话开场执行完整动作。
- [X] 6.2 Introduce：说明 AI 护理助手身份、职责边界和不能替代医护诊疗的范围。
- [X] 6.3 Communicate：说明评估目的、流程、预计配合方式，并在阶段转换时自然提示。
- [X] 6.4 Ask：询问不适、担心、待解决问题和帮助需求；结合量表 Task-todo 自然提问。
- [X] 6.5 Respond：先回应患者当前内容，再自然过渡到一个待评估问题；支持入院生活问题和护理指导。
- [X] 6.6 Exit：仅在结构化进度完整后礼貌结束并说明下一步护理安排。
- [X] 6.7 药物过敏、吸烟饮酒、手术等特征触发追问、宣教或知情同意工具。
- [X] 6.8 提示词禁止照抄字段名、禁止假共情、禁止重复称呼、禁止一次连续堆叠多个问题。
- [X] 6.9 修订机械化 patient_text，并识别不应直接询问患者的评分、护理计划和交班字段。

## 7. 前端同步

- [X] 7.1 患者任务在 Task-todo 和首问准备期间显示后台准备状态。
- [X] 7.2 对话进度只使用后端结构化进度事件和快照。
- [X] 7.3 后台 Extraction/Schedule 失败不解除患者输入能力，也不永久显示“等待 AI”。
- [X] 7.4 仅在后端 task_status_updated 确认完成后切换提交完成界面。

## 8. 验证、审查与交付

- [X] 8.1 运行后端单元测试和 Redis/PostgreSQL 集成测试。
- [X] 8.2 运行前端 Vitest、lint、typecheck 和 production build。
- [X] 8.3 使用真实浏览器验证首问预热、连续对话、后台失败降级和最终完成。
- [X] 8.4 记录代码审查与 BUG 修复结果。
- [X] 8.5 更新 backend/AGENTS.md、frontend/AGENTS.md、API 文档和部署说明。
- [ ] 8.6 测试通过后提交功能分支、合并本地 main 并删除功能分支。

### 真实联调补充记录

- 2026-08-18：任务 `96` 验证 Dialog 不等待 Schedule/Extraction；首问预热成功，患者消息后先返回自然下一问，Extraction 随后将进度从 `0/38` 更新为 `1/38`。
- 2026-08-18：任务 `98` 验证 Schedule Agent 真实模型规划成功；此前任务 `96/97` 暴露 DashScope `response_format=json_object` 要求提示词包含 `json`，已补充约束并回归测试。
- 2026-08-18：浏览器患者端 SSE 保持连接，控制台错误为空；首问符合 CICARE 开场并先回应患者再过渡提问。
