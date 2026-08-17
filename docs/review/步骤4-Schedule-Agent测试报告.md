# 步骤4：Schedule Agent 完整测试报告

## 1. 结论

Schedule Agent 已完成单元、集成、真实 Celery worker 和真实模型端到端测试，
满足步骤4验收要求，可以合并回本地 `main`。

最终结果：

| 项目 | 结果 |
|---|---:|
| 单元测试 | 72 passed |
| 集成测试 | 10 passed |
| 真实模型 E2E | 1 passed |
| 最终统一回归 | 83 passed |
| 步骤4目标模块综合覆盖率 | 96% |
| Ruff | 通过 |
| Mypy | 10 个源文件通过 |
| compileall | 通过 |
| 真实 Celery worker | 通过 |

测试日期：2026-08-17
测试分支：`test/schedule-agent`
测试工作树：`D:\A-AICodeWork\medical-evaluate-schedule-agent-test`

## 2. 测试环境

- Windows 11、PowerShell、Python 3.11.10
- PostgreSQL 16 Docker：`medical-evaluate-postgres`
- Redis 7 Docker：`medical_redis`
- Celery 5.6.3，Windows `solo` pool
- OpenAI 兼容接口：阿里云百炼
- 真实模型：`qwen-plus`

测试期间未把 API 密钥写入代码、配置模板或 Git 变更。

## 3. 自动化测试结果

### 3.1 单元测试

执行命令：

```powershell
uv run pytest tests/unit-test -q
```

结果：

```text
72 passed in 21.38s
```

覆盖内容：

- Schedule Agent 每 5 轮触发、结构化语义判断和 fail-open；
- 已完成问题、剩余问题和状态恢复；
- 工具调用名称、参数、否定语义和损坏记录；
- 提示词与上下文格式；
- OpenAI 兼容模型配置、Agent 绑定和环境变量密钥解析；
- Redis Stream 解码、约束事件、会话结束事件和检查点；
- Celery 任务组装、重试和按进程基础设施初始化；
- 量表目录导入映射、审核状态和幂等逻辑；
- `medagent` 与 `app` 的单向依赖边界和 wheel 打包。

### 3.2 集成测试

集成测试使用真实 PostgreSQL 和 Redis，结果如下：

| 测试组 | 结果 |
|---|---:|
| 领域持久化 | 4 passed |
| 真实量表目录导入 | 3 passed |
| Redis Stream 与事件往返 | 2 passed |
| Alembic 临时数据库升降级 | 1 passed |
| 合计 | 10 passed |

量表导入和领域持久化测试使用事务回滚；Alembic 测试创建独立临时数据库并在
结束后删除；Redis 测试使用唯一临时键并清理。

首次整套集成命令被外层执行工具超时中断，遗留 2 个随机命名的 Alembic 临时
数据库。提交前残留审计已精确识别并删除这 2 个测试库；复查结果为 0 个临时库。

### 3.3 真实模型 E2E

执行命令：

```powershell
uv run pytest tests/e2e-test -q
```

结果：

```text
1 passed in 26.80s
```

测试通过真实 `DASHSCOPE_API_KEY` 和 OpenAI 兼容接口调用 `qwen-plus`，覆盖：

1. 否定吸烟；
2. 正常追问；
3. 共情后继续评估；
4. 必要宣教；
5. 回答插入问题后主动拉回评估；
6. 明显偏离量表；
7. 重复询问已回答问题。

准确率断言严格设置为 `> 85%`，本次执行通过。缺少真实密钥时用例只允许明确
skip，不允许以 Mock 结果冒充 E2E。

### 3.4 最终统一覆盖率回归

单元、集成和 E2E 统一执行结果：

```text
83 passed in 343.98s
```

步骤4目标模块覆盖率：

| 模块 | 覆盖率 |
|---|---:|
| `app.workers.schedule_agent_runner` | 100% |
| Schedule Agent models | 100% |
| Schedule Agent prompts | 100% |
| 量表目录导入器 | 96% |
| Celery worker runtime | 95% |
| 应用配置 | 95% |
| Schedule Agent 核心 | 93% |
| 量表问题加载器 | 91% |
| 综合 | 96% |

覆盖率统一运行出现 15 条 SQLAlchemy 第三方 `GenericFunction already registered`
警告。警告仅在覆盖率进程中先后加载 PostgreSQL 集成与 Alembic 测试时出现，
各测试组独立运行均通过且无业务告警，不影响迁移、查询或测试结论。

## 4. 真实 Celery worker 验证

测试启动了独立 Windows `solo` worker，消费：

- `schedule_queue`
- `default`

worker 成功注册 `app.celery_app.tasks.schedule_agent_worker`，启动日志确认 Redis
同步和异步客户端已初始化。随后向 `schedule_queue` 提交烟测任务：

```json
{
  "session_id": "worker-smoke-session-3",
  "scale_codes": ["__worker_smoke_missing__"]
}
```

Celery backend 的真实结果：

```json
{
  "status": "SUCCESS",
  "result": {
    "status": "failed",
    "reason": "no_questions_loaded"
  },
  "queue": "schedule_queue",
  "retries": 0
}
```

该结果证明 worker 已完成任务注册、Redis broker/backend 连接、进程运行时初始化、
Schedule Agent 组装和真实 PostgreSQL 查询。验证结束后已停止 worker，删除临时
模型配置，并清理已知烟测结果键。

本机 Docker/Kombu 首次建立连接约有 20 秒冷启动延迟；worker 就绪后同类任务
执行约 1 秒。这属于当前开发环境连接延迟，未发现任务逻辑阻塞。

## 5. 真实量表导入结果

已将 `docs/structured/assessment-scales` 的真实数据幂等导入开发数据库：

| 对象 | 数量 |
|---|---:|
| 量表 | 5 |
| 版本 | 5 |
| 分组 | 10 |
| 问题 | 90 |
| 选项 | 315 |
| 规则 | 7 |
| 动作 | 53 |

第二次导入新增数全部为 0，`skipped_versions = 5`。源文件状态均为
`pending_review`，数据库中的量表和版本保持“审核中”，没有擅自发布。

## 6. 测试期间发现并修复的问题

1. SDK 层逆向导入 `app.*`，破坏分层边界；
2. Schedule Agent 导入不存在的提示词模块；
3. Redis Stream bytes 字段与字符串比较导致事件被忽略；
4. worker 调用 Redis wrapper 不存在的 `setex`；
5. `openai` 依赖未声明；
6. wheel 未打包 `medagent`；
7. LLM 配置结构不符合通用模型列表要求；
8. `$ENV` API key 未解析；
9. 问题进度使用字符串包含和 `list.index()`，存在误判；
10. 工具完整性通过回复文字猜测，没有检查真实 `tool_calls`；
11. “不吸烟”会误触发戒烟工具检查；
12. 真实量表目录缺少幂等数据库导入器；
13. BMI、年龄分和其他量表引用分等派生题会被提问；
14. Pydantic v1 事件配置产生弃用警告；
15. pytest 辅助类被误收集；
16. 测试路径注入掩盖 `medagent` 打包缺陷；
17. 独立 Celery worker 未初始化数据库和 Redis。

上述问题均已修复并进入自动化回归。

## 7. 剩余边界与建议

- 真实量表仍处于“审核中”，需要临床审核完成后才能发布；
- 真实模型 E2E 当前为 7 类核心语义场景，生产阶段仍应持续采集误判样本；
- Schedule Agent 与 Dialog Agent 的协作 E2E 依赖步骤5，本轮按要求未开发；
- 任务启动、状态查询和停止 API 属于步骤9，不纳入步骤4失败项；
- 生产多 worker 容量和故障转移压测应在部署拓扑确定后执行。

## 8. 审查结论

步骤4代码分层、配置、数据导入、运行器、Celery 生命周期和真实模型链路均已
通过验证。未发现阻止合并的问题，建议合并 `test/schedule-agent` 到本地
`main`，并删除该测试分支及工作树。
