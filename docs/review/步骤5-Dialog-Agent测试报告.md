# 步骤5：Dialog Agent 测试报告

## 1. 结论

Dialog Agent 的文本主链路、SDK/App 分层、中间件、工具调用、Redis/PostgreSQL
适配和 Celery 预热已完成自动化与真实环境验证，可以合并本地 `main`。

豆包真实全双工语音 E2E 未通过也未伪造：当前环境缺少 API Key、App ID、
Resource ID，且示例中的 TTS `ws_binary` 地址尚未证明与当前会话事件协议一致。
因此本报告不对豆包生产可用性作通过结论。

## 2. 测试环境

- Windows 11、PowerShell、Python 3.11.10
- PostgreSQL 16：`medical-evaluate-postgres`
- Redis 7：`medical_redis`
- Celery 5.6.3，Windows `solo` pool
- OpenAI 兼容真实模型：阿里云百炼 `qwen-plus`
- 独立分支：`test/dialog-agent`
- 独立工作树：`D:\A-AICodeWork\medical-evaluate-dialog-agent-test`

## 3. 结果汇总

| 层级 | 结果 | 说明 |
| --- | --- | --- |
| Dialog 专项单元 | 66 passed | 引擎、编排、中间件、工具、Prompt、Celery、架构 |
| 全量单元回归 | 138 passed | 步骤1-4无回归 |
| 真实集成 | 14 passed | PostgreSQL、Redis、Alembic、量表导入与Agent协作 |
| 真实模型 E2E | 3 passed | Dialog普通对话、Dialog工具闭环、Schedule七场景 |
| Dialog 覆盖率 | 95% | 门槛为90% |
| Ruff | passed | 指定生产代码与测试 |
| Mypy | passed | 13个Dialog相关生产文件 |
| compileall | passed | `app` 与 `packages/medagent` |
| Celery烟测 | passed | `dialog_queue`、真实DB/Redis初始化、无量表失败分支 |
| 豆包真实语音 | blocked | 缺凭据和已验证协议endpoint |

## 4. 修复的主要缺陷

1. 修复 Dialog 公共导入路径错误和不存在的事件发布器导入。
2. 移除 `medagent` 对 `app.*` 的反向依赖，新增 App 依赖注入协议与适配层。
3. 统一 Schedule/Dialog 使用 `dialog_stream:{session_id}`，按游标避免重复注入。
4. 修复 Celery Dialog worker 未初始化 PostgreSQL/Redis 的问题。
5. 适配 websockets 17 的 `additional_headers` 与连接状态差异。
6. 聚合 OpenAI 流式工具名称和 JSON 参数分片。
7. 修复文本输入晚于 before middleware，导致关键词无法命中的问题。
8. 修复患者/AI历史保存、状态管理器参数和失败资源释放。
9. 修复 Prompt 未替换变量、开发者措辞和“饮酸”笔误。
10. 统一模型异常脱敏，避免供应商错误泄漏给患者。
11. 工具占位 ID 改为 UUID，避免固定 ID 被误当作真实临床记录。
12. 修复文本工具调用回传后不继续调用模型、患者可能收到空回复的问题；
    增加最多4轮工具响应保护，并用真实模型验证闭环。
13. 补齐 `agent_models.dialog_agent: qwen-plus` 文本降级配置绑定。

## 5. 真实基础设施验证

### Redis

- `ConstraintEvent` 可被 Dialog middleware 解码并只消费一次；
- 消费游标设置1小时 TTL；
- `DialogTurnEvent` / `ToolCallEvent` 字段可供 Schedule runner 消费；
- 活动时间戳设置 TTL 并可在结束时清理；
- 测试使用 UUID 键，结束后无测试键残留。

### PostgreSQL

- Dialog Agent 一轮文本对话写入患者原话与 AI 回复；
- 两条消息共享同一 `turn_no`；
- 集成测试使用外层事务回滚，不保留患者或消息数据。

### Celery

- 独立 `dialog-step5-smoke` worker 注册并消费 `dialog_queue`；
- worker 初始化真实 Redis 和 PostgreSQL；
- 不存在量表编码返回
  `{"status": "failed", "reason": "no_questions_loaded"}`；
- 任务执行耗时43.39秒；worker启动到 ready 约127秒，功能通过但应作为
  Windows开发环境性能观察项；
- worker、子进程、结果键和日志均已清理。

## 6. 真实模型验证

- 普通文本：真实 `qwen-plus` 完成患者输入与流式中文回复。
- 工具闭环：真实模型调用 `trigger_consent_form`，本地占位工具执行，
  结果回传后模型继续生成患者可见回复。
- Schedule 回归：七类偏离场景准确率继续满足 `>85%`。
- 全程未使用 Mock 代替模型返回。

## 7. 阻塞项与风险

### 豆包真实语音

执行需要：

- `DOUBAO_API_KEY`
- App ID
- Resource ID
- 与 `session.create/update`、音频流、工具调用事件匹配的真实 WebSocket endpoint
- 一段符合采样率和编码要求的最小 PCM 音频

当前上述条件不完整，不能确认 `DoubaoVoiceEngine` 的真实生产协议兼容性。
上线豆包语音前必须在独立测试分支完成真实 E2E。

### 其他遗留

- `interaction_rule` ORM 已存在，但关键词规则 JSON 结构和临床审核数据尚未落地，
  当前仍使用内置最小规则；不能宣称数据库规则已启用。
- 宣教、知情同意和播放音频工具仍有批次B占位行为，不代表临床流程完成。
- Windows Celery/基础设施建立连接偏慢，后续应单独分析连接超时与启动性能。

## 8. 复现命令

在 `backend` 目录执行：

```powershell
uv sync --extra dev
uv run pytest tests/unit-test -q
uv run pytest tests/integ-test -q
$env:DASHSCOPE_API_KEY = "真实密钥"
uv run pytest tests/e2e-test -q -m real_llm
```

覆盖率：

```powershell
$dialogTests = Get-ChildItem tests/unit-test -Filter "test_dialog_*.py" |
  Select-Object -ExpandProperty FullName
uv run pytest $dialogTests -q `
  --cov=medagent.agents.service_agent.dialog_agent `
  --cov=medagent.agents.middleware `
  --cov=app.workers.dialog_agent_runtime `
  --cov-report=term-missing `
  --cov-fail-under=90
```

---

**执行时间**：2026-08-17
**状态**：可执行范围通过；豆包真实语音 E2E 阻塞
