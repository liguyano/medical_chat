# 步骤5：Dialog Agent 完整测试计划

## 1. 测试目标

验证 Dialog Agent 从 SDK 导入、提示词、双引擎、中间件、工具调用、状态与历史
持久化、Redis Stream 事件到 Celery 预热任务的完整链路，确保：

- `medagent` SDK 不反向依赖 `app.*`；
- Dialog Agent 公共导入路径可直接使用；
- 豆包语音与 OpenAI 兼容文本引擎输出统一事件；
- CICARE 六步、评估任务和动态约束能够正确注入；
- 中间件按顺序执行，单个中间件异常不阻塞患者主对话；
- 工具调用、事件发布、状态保存与 PostgreSQL 历史持久化契约一致；
- 独立 Celery worker 能初始化 PostgreSQL 与 Redis 并执行预热任务；
- 真实模型或真实语音环境缺失时明确报告，不以 Mock 冒充 E2E。

## 2. 已确认的基线阻断项

- [X] Dialog Agent 公共导入失败：相对导入错误指向不存在的
  `medagent.agents.service_agent.middleware`
- [X] 事件中间件导入不存在的 `app.managers.event_publisher`
- [X] Dialog SDK 与 middleware 直接导入多个 `app.*`，违反仓库分层规则
- [X] Schedule Constraint 读取 `constraint_stream:*` 和 `data` 字段，但 Schedule
  Agent 实际向 `dialog_stream:*` 发布扁平 `ConstraintEvent`
- [X] Dialog Celery 任务没有调用 worker runtime 初始化
- [X] 当前 `websockets 17.0.1` 使用 `additional_headers`，实现仍使用旧
  `extra_headers`，且连接对象不再保证 `.closed` 属性
- [X] TextChatEngine 未聚合 OpenAI 流式工具参数分片
- [X] 文本输入在 before middleware 之后才进入引擎，关键词中间件无法看到输入
- [X] 开发文档声称 `interaction_rule`、`dialogue_script` 表未就绪，但批次A ORM
  和迁移中已经存在，需要以数据库事实来源重新核对

上述问题必须先由自动化测试稳定复现，再在本测试分支修复。

## 3. 测试环境与隔离

- [X] Windows 11、PowerShell、Python 3.11
- [X] 独立分支：`test/dialog-agent`
- [X] 独立 worktree：`D:\A-AICodeWork\medical-evaluate-dialog-agent-test`
- [X] pytest、pytest-asyncio、pytest-cov
- [X] Docker PostgreSQL 16
- [X] Docker Redis 7
- [X] Windows Celery `solo` worker
- [X] 真实 OpenAI 兼容文本模型
- [X] 真实豆包语音 WebSocket（仅在密钥与协议参数齐全时执行）

## 4. SDK 架构与公共导入测试

- [X] `medagent.agents.service_agent.dialog_agent` 可直接导入
- [X] wheel 安装后在隔离 Python 进程可导入
- [X] `dialog_agent/` 和 `middleware/` 不含 `app.*` 导入
- [X] App 层通过依赖注入组装状态、历史、事件和超时适配器
- [X] Dialog Agent 数据模型与 Schedule Agent `QuestionTask` 契约统一

计划文件：

- `backend/tests/unit-test/test_dialog_architecture.py`
- `backend/tests/unit-test/test_dialog_runtime.py`

## 5. 双引擎单元测试

### 5.1 DoubaoVoiceEngine

- [X] 会话创建使用 websockets 17 兼容参数和 Bearer 认证
- [X] `session.create` 包含会话号、对话号、模型、工具和音频格式
- [X] 非 `session.created` 响应应失败并安全关闭连接
- [X] PCM bytes 正确 base64 编码并按 append/commit 发送
- [X] 未连接或输入类型错误时返回明确错误
- [X] 文本、音频、ASR、工具调用、完成和错误事件正确归一化
- [X] 非 JSON 二进制帧按音频事件处理
- [X] 非法工具参数不击穿事件循环
- [X] 响应超时产生 error 事件
- [X] 工具结果和动态约束消息格式正确
- [X] close 幂等
- [X] 断线后按既定重试上限重连，不无限循环

### 5.2 TextChatEngine

- [X] 创建会话、文本输入和输入类型校验
- [X] OpenAI 兼容文本流正确聚合
- [X] 跨 chunk 工具名称与 JSON 参数正确聚合
- [X] 工具调用后保存合法 assistant/tool 上下文
- [X] 模型异常转换为 error 事件
- [X] 动态约束和工具列表更新
- [X] 关闭引擎时关闭 AsyncOpenAI 客户端

计划文件：

- `backend/tests/unit-test/test_dialog_engines.py`

## 6. Dialog Agent 编排测试

- [X] initialize 构建 CICARE prompt、注册工具并保存初始状态
- [X] 文本输入在中间件执行前写入 context
- [X] 语音 ASR 文本正确写入 context 和 PostgreSQL 历史
- [X] 文本/音频/工具/完成/error 事件分发正确
- [X] 工具调用执行并将结果回传引擎
- [X] 动态约束通过 `engine.update_session` 注入
- [X] 患者与 AI 消息按同一轮次持久化
- [X] after middleware 发布完整患者问题、AI回答和 tool_calls
- [X] 中间件、状态或历史依赖异常不泄漏敏感信息
- [X] close 释放引擎资源

计划文件：

- `backend/tests/unit-test/test_dialog_agent.py`

## 7. Middleware 测试

- [X] MiddlewareChain before/after 顺序稳定
- [X] 单个 middleware 失败时后续 middleware 继续执行
- [X] 关键词命中、去重和否定语义正确
- [X] ConstraintEvent 按 Redis Stream 真实扁平字段解码
- [X] 约束消费保存 last event id，不在每轮重复注入
- [X] DialogTurnEvent 和 ToolCallEvent 字段符合 Schedule Agent 契约
- [X] 发布失败只记录错误，不中断患者主对话
- [X] before/after 更新活动时间戳
- [X] 缺失 session_id 时安全跳过

计划文件：

- `backend/tests/unit-test/test_dialog_middleware.py`

## 8. Prompt 与工具测试

- [X] system prompt 包含 CICARE 六步、沟通风格、患者信息和完整任务列表
- [X] 必填/选填标识和动态约束正确
- [X] prompt 中不包含未替换的模板变量或面向开发者的 TODO
- [X] 三个工具 Schema 符合 OpenAI function calling 格式
- [X] 工具参数枚举、默认级别和非法参数处理
- [X] 未知工具返回结构化失败
- [X] 优雅桩不伪造已签署、已宣教等临床完成状态

计划文件：

- `backend/tests/unit-test/test_dialog_prompt_tools.py`

## 9. Celery 与应用层组装测试

- [X] 缺少 scale_codes、模型绑定或语音配置时明确失败
- [X] text/doubao 引擎按配置正确构建
- [X] API key 环境变量正确解析
- [X] worker runtime 在加载量表前初始化
- [X] 预热成功返回引擎类型和问题数
- [X] 未处理异常交由 Celery retry
- [X] Windows `solo` worker 注册并消费 `dialog_queue`

计划文件：

- `backend/tests/unit-test/test_dialog_celery.py`

## 10. 真实集成测试

- [X] Redis：Schedule Agent ConstraintEvent → Dialog constraint middleware
- [X] Redis：DialogTurnEvent / ToolCallEvent → Schedule Agent runner 可消费
- [X] Redis：状态、活动时间戳和约束 checkpoint 无残留
- [X] PostgreSQL：DialogHistoryManager 保存患者/AI同轮消息
- [X] PostgreSQL：已发布量表问题可用于预热
- [X] Celery：真实 worker 对缺失量表或烟测量表返回预期结果
- [X] 测试事务、临时键和 worker 进程全部清理

计划文件：

- `backend/tests/integ-test/test_dialog_agent_redis.py`
- `backend/tests/integ-test/test_dialog_agent_postgres.py`

## 11. 端到端测试

### 11.1 真实 OpenAI 兼容文本模型

- [X] 真实 `qwen-plus` 完成患者输入与流式中文回答
- [X] 真实模型发起知情同意工具调用
- [X] 工具执行结果回传后继续生成患者可见回复
- [X] Schedule 约束通过真实 Redis 在下一轮只注入一次
- [X] Dialog 事件、Redis 状态和 PostgreSQL 历史分别完成真实集成验证

### 11.2 真实豆包语音（阻塞）

- [ ] 仅使用真实 `DOUBAO_API_KEY` 和实际协议参数
- [ ] 建立真实 WebSocket 会话
- [ ] 发送最小合法 PCM 音频
- [ ] 收到 ASR、文本/音频或明确协议错误
- [ ] 动态约束和关闭会话成功

如缺少密钥、App ID、Resource ID 或实际 endpoint，必须将真实豆包 E2E 标记为
阻塞并向用户报告，不能用本地 fake WebSocket 代替真实 E2E 结论。

实际文件：

- `backend/tests/e2e-test/test_dialog_agent_text_llm.py`
- 豆包测试文件未创建：缺少真实执行条件时禁止提交伪 E2E

## 12. 静态质量与验收标准

- [X] 步骤5新增单元、集成、E2E 测试全部通过
- [X] 既有步骤1-4测试无回归
- [X] Dialog Agent 目标模块综合覆盖率不低于 90%
- [X] Ruff、Mypy、compileall、`git diff --check` 通过
- [X] 没有真实密钥进入 Git
- [X] 没有测试数据库、Redis key、Celery 结果或后台进程残留
- [X] 生成 `docs/review/步骤5-Dialog-Agent测试报告.md`
- [ ] 测试分支合并回本地 `main`
- [ ] 删除测试 worktree 和 `test/dialog-agent` 分支

---

**创建时间**：2026-08-17
**执行结果**：

- Dialog 专项单元测试 66 项通过，目标模块覆盖率 95%；
- 全量单元测试 138 项、真实集成测试 14 项通过；
- 真实模型 E2E 3 项通过（Dialog 2 项、Schedule 回归 1 项）；
- Windows `solo` Dialog worker 烟测通过；
- 豆包真实语音 E2E 因缺少 API Key、App ID、Resource ID 及已验证 endpoint 阻塞；
- 详细结论见 `docs/review/步骤5-Dialog-Agent测试报告.md`。

**状态**：可执行测试完成，待合并与清理
