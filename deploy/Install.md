# Install.md
本文档记录系统启动的完整部署/启动指南, 用户可按照本文档的步骤, 完整启动项目. 依赖中间件全部使用 Docker 容器启动.
> 暂时默认 本地环境部署 启动项目, 先不使用 Docker 打包部署启动项目.

# 1. 数据库部署指南

## PostgreSQL 配置

本项目已使用 Docker 部署 PostgreSQL 开发数据库.

| 项目 | 值 |
| --- | --- |
| 服务名 | `postgres` |
| 容器名 | `medical-evaluate-postgres` |
| 镜像 | `postgres:16-alpine` |
| 数据库 | `medical_evaluate` |
| 用户名 | `medical` |
| 密码 | `medical_dev_password` |
| 主机 | `localhost` |
| 宿主机端口 | `15432` |
| 容器端口 | `5432` |
| 数据卷 | `medical_evaluate_pgdata` |

## 连接信息

```text
postgresql://medical:medical_dev_password@localhost:15432/medical_evaluate
```


## redis 配置




# 2. 后端启动指南

## Step1：启动依赖服务

在项目根目录执行：

```powershell
docker compose up -d postgres redis
```

## Step2：创建配置

```powershell
Copy-Item config.example.yaml config.yaml
$env:DASHSCOPE_API_KEY="你的模型 API Key"
```

## Step3：安装后端依赖

```powershell
Set-Location backend
uv sync
```

## Step4：初始化数据库

```powershell
uv run alembic upgrade head
uv run python -m app.commands.seed_demo
```

`seed_demo` 会幂等写入 5 个医护演示账号、10 位在院患者、量表和关键词规则。
医护密码只以 bcrypt 哈希保存，重复执行不会新增重复账号。
这些凭据只用于本地开发联调，生产环境禁止执行演示种子或沿用 `123456`。

## Step5：启动 API 服务

```powershell
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

API 地址：`http://127.0.0.1:8000`

健康检查：

```powershell
Invoke-WebRequest http://127.0.0.1:8000/health
```

## Step6：启动 Agent Worker

分别打开三个 PowerShell 窗口，进入 `backend` 目录后执行：

```powershell
uv run celery -A app.celery_app.celery_config:celery_app worker --pool=solo --concurrency=1 --without-gossip --without-mingle --without-heartbeat -Q dialog_queue -n dialog-real@%h --loglevel=info
```

```powershell
uv run celery -A app.celery_app.celery_config:celery_app worker --pool=solo --concurrency=1 --without-gossip --without-mingle --without-heartbeat -Q schedule_queue -n schedule-real@%h --loglevel=info
```

```powershell
uv run celery -A app.celery_app.celery_config:celery_app worker --pool=solo --concurrency=1 --without-gossip --without-mingle --without-heartbeat -Q extraction_queue -n extraction-real@%h --loglevel=info
```

每个队列只启动一个 Worker。Worker 进程常驻，Agent 按首问或患者答案按需创建，
单轮完成后释放。修改代码或 `config.yaml` 后必须重启 Worker。

任务创建阶段由 `schedule_queue` 先生成 Task-todo，再由 `dialog_queue` 预热和生成首问。
患者对话阶段三个队列彼此独立，`schedule_queue` 或 `extraction_queue` 卡住不得阻塞
`dialog_queue`。进度完成后 Extraction 会向 `dialog_queue` 追加 CICARE Exit 任务。

另开一个 PowerShell 窗口启动补偿扫描：

```powershell
uv run celery -A app.celery_app.celery_config:celery_app beat --loglevel=info
```

Beat 每 30 秒补派因 Worker 重启或任务丢失而未生成下一问的患者答案。

## Step7：真实模型检查

`config.yaml` 中三个 Agent 必须绑定测试语言模型：

```yaml
agent_models:
  dialog_agent:
    language: qwen3.5-flash
  schedule_agent:
    language: qwen3.5-flash
  extraction_agent:
    language: qwen3.5-flash
```

启动后日志应出现：

```text
[LLM] 创建真实语言模型客户端
HTTP Request: POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions "HTTP/1.1 200 OK"
```

Extraction 成功日志：

```text
[Extraction Agent] 真实模型结构化响应成功
```


# 3. 前端启动指南

## Step1：安装运行环境

安装 Node.js 20.9 或更高版本，并启用项目指定的 pnpm：

```powershell
corepack enable
corepack prepare pnpm@10.26.2 --activate
node --version
pnpm --version
```

## Step2：进入前端目录

```powershell
Set-Location frontend
```

## Step3：创建环境配置

```powershell
Copy-Item .env.example .env.local
```

默认使用 Mock 数据。如需连接后端，编辑 `.env.local`：

```dotenv
NEXT_PUBLIC_DATA_MODE=api
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_DIALOG_TRANSPORT=websocket
NEXT_PUBLIC_API_TIMEOUT_MS=15000
```

## Step4：安装依赖

```powershell
pnpm install
```

## Step5：启动开发环境

```powershell
pnpm dev
```

浏览器访问：

- 医护端：`http://localhost:3000/nurse`
- 患者端：`http://localhost:3000/patient`

## Step6：生产环境启动

生产构建和生产服务必须按“停止旧服务 → 构建 → 启动”的顺序执行。
禁止在旧的 `pnpm start` 仍运行时执行 `pnpm build` 后继续复用旧进程。
旧进程会保留上一版路由和资源清单，而新的构建会替换磁盘上的 chunk，
两者混用会导致浏览器出现 `ChunkLoadError`。

如果生产服务已经运行，先在对应 PowerShell 窗口按 `Ctrl+C` 停止。
随后确认 3000 端口已释放：

```powershell
Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue
```

命令无输出后，再执行：

```powershell
pnpm build
pnpm start
```

每次重新执行 `pnpm build` 后都必须重新启动 `pnpm start`。不要让多个
`pnpm dev` 或 `pnpm start` 实例同时监听 3000 端口。

浏览器访问：

- 医护端：`http://localhost:3000/nurse`
- 患者端：`http://localhost:3000/patient`

# 4. 前后端联调指南

## Step1：演示账号

医护端（所有演示账号密码均为 `123456`）：

| 账号 | 姓名 | 科室 | 密码 |
| --- | --- | --- | --- |
| `N001` | 李护士 | 心内科 | `123456` |
| `N002` | 王护士 | 老年医学科 | `123456` |
| `N003` | 赵护士 | 消化内科 | `123456` |
| `N004` | 陈护士 | 呼吸与危重症医学科 | `123456` |
| `N005` | 刘护士 | 骨科 | `123456` |

医护端 API 模式登录接口为 `POST /api/auth/staff/login`，登录成功后使用
HttpOnly Cookie `medical_staff_session` 访问护士业务接口。退出登录调用
`POST /api/auth/staff/logout`。

患者端不使用固定工号，使用住院登记信息登录：

| 患者 | 身份证号 | 手机号 |
| --- | --- | --- |
| 张桂芳 | `110101194803120010` | `13800000001` |
| 李国强 | `110101195507250026` | `13800000002` |
| 王秀兰 | `110101194011020038` | `13800000003` |
| 陈建军 | `110101196801180043` | `13800000004` |
| 赵敏 | `110101198509300051` | `13800000005` |
| 周海燕 | `110101197206150028` | `13800000006` |
| 孙志伟 | `110101196212080035` | `13800000007` |
| 杨秀梅 | `110101197904220026` | `13800000008` |
| 黄建国 | `110101195010090019` | `13800000009` |
| 林晓莉 | `11010119920214002X` | `13800000010` |

患者端 API 联调页面会提供以上 10 位患者的“填充姓名”快捷按钮，点击后自动写入
身份证号和手机号，再点击“核验并进入”即可登录。快捷按钮只在本地联调页面显示，
不会改变患者登录校验逻辑，也不会替代真实住院身份核验。

## Step2：联调流程

1. 医护端登录，选择患者并发布 AI 对话任务。
2. 患者端打开 `http://localhost:3000/patient`。
3. 输入身份证号和手机号登录。
4. 在“任务中心”选择本人任务并开始评估。
5. 医护端进入任务详情或实时监控查看对话与抽取结果。

患者端不输入任务编号。任务编号只用于医护端查看、后台关联和审计。

未办理入院的患者登录时提示：

```text
您还未办理入院，暂不能进入患者端
```

医护端和患者端可在同一浏览器的不同标签页打开，登录状态互不覆盖。
