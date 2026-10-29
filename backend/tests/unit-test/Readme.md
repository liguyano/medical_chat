# 单元测试

`test_topic_guided_assessment.py` 验证话题引导规则进入共享 Dialog、文本首问及语音剩余题提示，
并覆盖 Schedule 允许相关过渡与 Extraction 禁止场景推断的输入契约；不代表已验证真实模型问法或准确性。
同时覆盖引入后继续同一未完成目标题、跳过已有答案、历史恢复不重复引入及感觉题不误判为疼痛评分。
`test_topic_turn_planner.py` 覆盖按话题跨题序选择相关缺项、拒绝虚构或已完成目标，以及纯通话确认与夹带不适的区分；Qwen 客户端测试覆盖重连时保留最新约束和最近交流。

患者住院默认值测试 `test_patient_encounter_defaults.py` 覆盖省略入院时间时自动生成 UTC 时间、默认在院及历史时间兼容。
同时覆盖自动住院号的不同请求不重复，以及床号、护理级别、入院来源的默认占位值。

在 `backend` 目录执行：

```powershell
uv run pytest tests/unit-test -v
```

本目录测试不得连接 PostgreSQL、Redis 或外部模型；外部依赖必须使用 fake/mock/stub。

本目录新增字段抽取契约测试，覆盖答案类型边界转换、历史别名拒绝以及增量上下文拼装。

Schedule Agent 单元测试覆盖：

- SDK 分层依赖、问题任务与输出 Schema；
- 每5轮检查、LLM 结构化响应、失败放行与进度恢复；
- 工具调用完整性、否定语义和损坏事件降级；
- OpenAI 兼容模型配置、提示词、Celery 组装、按进程运行时初始化和运行器检查点。

Dialog Agent 单元测试覆盖：

- SDK/App 分层、公共导入和依赖注入组装；
- 豆包 WebSocket 事件归一化、文本模型流式输出和工具参数分片；
- 工具结果回传后的后续模型响应闭环与最大轮次保护；
- CICARE 提示词、工具 Schema、关键词/约束/事件/超时中间件；
- Celery text/doubao 配置分流、运行时初始化和失败重试。

覆盖率命令：

```powershell
uv run pytest tests/unit-test `
  --cov=medagent.agents.service_agent.schedule_agent `
  --cov=app.managers.assessment_loader `
  --cov=app.managers.assessment_catalog_importer `
  --cov=app.workers.schedule_agent_runner `
  --cov=app.celery_app.runtime `
  --cov=app.configs.app_config `
  --cov-report=term-missing
```

语音诊断回归：`test_voice_diagnostics.py` 覆盖白名单落盘及目录无权限降级；`test_qwen_realtime_client.py` 覆盖重连失败日志关联与敏感信息不落盘，全部使用fake连接。
