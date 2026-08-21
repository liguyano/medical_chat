# 单元测试

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
