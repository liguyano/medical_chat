# 单元测试

在 `backend` 目录执行：

```powershell
uv run pytest tests/unit-test -v
```

本目录测试不得连接 PostgreSQL、Redis 或外部模型；外部依赖必须使用 fake/mock/stub。

Schedule Agent 单元测试覆盖：

- SDK 分层依赖、问题任务与输出 Schema；
- 每5轮检查、LLM 结构化响应、失败放行与进度恢复；
- 工具调用完整性、否定语义和损坏事件降级；
- OpenAI 兼容模型配置、提示词、Celery 组装、按进程运行时初始化和运行器检查点。

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
