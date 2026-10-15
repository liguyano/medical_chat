# medical_chat · 智能护理评估平台

面向住院患者入院阶段的护理评估平台，支持传统问卷与 AI 对话两种评估方式，并连接宣教、知情同意、医护复核、评估报告和护理计划流程。

项目采用前后端分离架构。患者端提供移动端评估入口，医护端负责患者、任务、会话监控和评估结果管理。

## 主要功能

| 方向 | 功能 |
| --- | --- |
| 患者评估 | 身份核验、任务查看、传统问卷、AI 文字与语音对话 |
| 护理交互 | 医学宣教、知情同意与签名、呼叫护士、人工介入 |
| 医护工作台 | 患者及住院记录管理、任务分配、对话监控与回放 |
| 结果管理 | 结构化答案、量表计分、护士复核、CGA 评估报告 |
| 护理计划 | 患者画像、护理计划生成、编辑与确认 |
| 配置与评价 | 量表、宣教材料、拦截规则及 AI 质量评价 |

前端支持 `mock` 和 `api` 两种数据模式。Mock 用于界面演示，其中模拟的 AI、语音等交互不代表已连接真实服务；真实模型与持久化能力需要启动后端、数据库、Redis 及相应 Worker，并配置模型服务。

## 技术架构

- **前端**：Next.js 16、React 19、TypeScript、Tailwind CSS、Zustand。
- **后端**：Python 3.11、FastAPI、SQLAlchemy、Alembic。
- **智能体**：项目内 `medagent` SDK，基于 LangChain / LangGraph 组织对话、调度与字段抽取。
- **数据与任务**：PostgreSQL、Redis / Redis Stream、Celery Worker 与 Beat。
- **实时通信**：SSE 推送对话及领域事件，WebSocket 连接实时语音网关。

## 目录导航

```text
medical_chat/
├─ backend/
│  ├─ app/                  # API、业务服务、领域模型与后台任务
│  ├─ packages/medagent/    # 智能体 SDK
│  └─ tests/               # 后端测试
├─ frontend/
│  ├─ src/app/             # 医护端与患者端页面
│  ├─ src/lib/             # 仓储、状态、API 与实时传输适配
│  └─ tests/               # 前端测试
├─ docs/                   # 开发计划、审查、问题记录与数据库设计
├─ deploy/                 # 镜像构建、生产配置模板与部署指南
├─ config.example.yaml     # 后端配置模板
├─ docker-compose.yml      # 本地 PostgreSQL / Redis
└─ start_medical_chat_all.bat # Windows 本机启动器
```

## 快速体验：前端 Mock 模式

准备 Node.js 20.9.0 或以上版本，以及项目声明的 pnpm 10.26.2。以下命令从仓库根目录执行，环境为 Windows PowerShell：

```powershell
Set-Location frontend
pnpm install
Copy-Item .env.example .env.local
pnpm dev
```

如果已有 `.env.local`，保留原文件，并确认 `NEXT_PUBLIC_DATA_MODE=mock`。切换数据模式或修改环境变量后需要重启前端。

打开开发服务器日志中的地址，默认入口如下：

| 入口 | 本地开发地址 |
| --- | --- |
| 医护登录 | <http://localhost:3000/nurse/login> |
| 患者核验 | <http://localhost:3000/patient> |
| 系统首页 | <http://localhost:3000/>，跳转医护登录 |

## 本地 API 联调

完整步骤见 [本地启动说明](deploy/本地启动说明.md) 和 [安装与部署指南](deploy/Install.md)。后端要求 Python 3.11、uv，以及已启动的 Docker Desktop（Linux containers）。

1. 在仓库根目录从 `config.example.yaml` 创建本地 `config.yaml`，按模板配置数据库、Redis 和模型服务；已有文件不要覆盖。
2. 使用根目录的 `docker-compose.yml` 启动 PostgreSQL 和 Redis。
3. 在 `backend` 目录执行 `uv sync`、`uv run alembic upgrade head`。需要本地演示数据时，再执行 `uv run python -m app.commands.seed_demo`。
4. 启动 FastAPI、分别消费 `dialog_queue` / `schedule_queue` / `extraction_queue` 的三个 Celery Worker，以及 Celery Beat；各进程使用独立终端。
5. 将前端 `.env.local` 的 `NEXT_PUBLIC_DATA_MODE` 改为 `api`，将 `NEXT_PUBLIC_API_BASE_URL` 设置为本地后端地址后启动前端。

本地联调的 API 健康检查地址为 `http://127.0.0.1:8000/health`。患者页面和后端地址应使用匹配的主机名及 Cookie 配置，避免混用本地页面与公网后端造成登录失效。

根目录的 `start_medical_chat_all.bat` 可以启动本机配套服务，但脚本包含固定项目路径和 npm 用户目录；换机器时请先核对脚本，或采用文档中的手动启动方式。不要重复启动同一组服务；结束调试时在各服务终端按 `Ctrl+C` 停止进程。

## 常用检查

在 `frontend` 目录执行：

```powershell
pnpm test
pnpm lint
pnpm typecheck
pnpm build
```

`pnpm check` 会依次运行上述检查。`pnpm dev` 运行开发服务；`pnpm start` 运行已生成的生产构建，构建后需要重新启动生产进程。

后端测试位于 `backend/tests/`，测试分层、环境准备与运行要求见 [后端模块说明](backend/AGENTS.md)。

## 正式部署

按照 [安装与部署指南的生产部署章节](deploy/Install.md) 发布：

- 本地构建带版本号的 Linux 镜像，服务器导入后运行 Compose，不在服务器构建源码。
- 宝塔宿主机 Nginx 负责 HTTPS 和反向代理；前端通过当前站点的 `/api`、`/api/sse/*` 与 `/api/ws/*` 访问后端。
- 前端镜像构建时传入最终 HTTPS `PUBLIC_ORIGIN`；域名变化需要重新构建前端镜像。
- PostgreSQL 和 Redis 不向公网发布端口；SSE 与 WebSocket 代理参数参照 [反向代理配置](deploy/baota-reverse-proxy.conf)。
- 生产配置与密钥保存在服务器；生产环境禁止执行 `seed_demo` 或使用演示账号。

本地开发地址仅用于开发联调，不作为生产访问配置。

## 配置与数据

`config.yaml`、前端 `.env.local`、生产环境文件和模型密钥属于本地或部署配置，不应提交。对话、身份证号、手机号、签名和音频等患者数据不得提交到 Git 或放入公开静态目录。

## 开发文档

- [仓库开发约定](AGENTS.md)
- [后端与智能体架构](backend/AGENTS.md)
- [前端架构与联调约定](frontend/AGENTS.md)
- [数据库业务设计](docs/sql/数据库表业务设计.md)
- [开发计划](docs/plan/)
- [代码审查记录](docs/review/)
