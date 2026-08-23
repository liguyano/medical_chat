# AGENTS.md
This file provides guidance to AI coding agents (Claude Code, Codex, and others) when working with code in this repository. It is the source of truth; the sibling `CLAUDE.md` imports it via `@AGENTS.md`.

It is the **monorepo orientation layer**: it maps the whole repo and points to the
module guides that own the depth. For anything inside a module, read that module's
guide rather than expecting full detail here:

- **[backend/AGENTS.md](backend/AGENTS.md)** — backend depth: harness/app split, agent &
  middleware chain, sandbox, MCP, skills, memory, IM channels, persistence/migrations,
  config system, test layout.
- **[frontend/AGENTS.md](frontend/AGENTS.md)** — frontend depth: Next.js App Router layout,
  thread/streaming data flow, code style, commands.

# 项目背景
本项目面向住院患者入院阶段的护理评估(两种方案: 传统问卷+AI对话)、知情同意宣讲、分级宣教、护理计划生成等功能, 开发一款 harness 智能体平台.
项目整体采用前后端分离架构.

## 约定
1. bash指令环境: 环境为 Windows-11 系统, 必须使用 Windows PowerShell 指令执行命令.
2. Git规范: 必须遵守本文档(`# 开发规范/## Git 规范`).
3. Docker 环境: 已安装 Docker Desktop, 假设无法使用 Docker, 请及时呼叫人类, 不要自己下载, 不要陷入死循环执行.
4. 始终遵守全文文件编码: UTF-8.
5. 始终在任务执行前回复: bro.
6. **禁止直接开发: 当接收到新需求时, 阅读相关代码, 思考新需求的可行性, 给出公正的意见, 可以反驳我的观点, 与我充分讨论必须确认可行方案, 才能开始开发, 开发前先制定完成新需求的计划文档.**
7. **任务结束前必须检查是否停止前后端进程, 避免后台残留进程占用, 影响IDE手动调试程序.**

## 技术栈
- 后端Web框架: FastAPI + 大模型流式输出(SSE) + asyncio + redis + redis-stream + Celery + Postgresql

- 后端Agent框架: langchain(Middleware)/Langgraph.

- 前端: Next.js + React + Tailwind-3/4 CSS 


# 项目目录结构
```text
./
├─ backend/
├─ ├─ app/                  # FastAPI 路由业务
├─ └─ packages/medagent     # 本项目开发的智能体SDK(agent framework)-(import: medagent.*)
├─ frontend/                # Next.js frontend (pnpm) — see frontend/AGENTS.md
├─ docs/                    # 开发文档保存
├─ ├─ plan/                 # 开发方案|计划|步骤
├─ ├─ review/               # 代码审查记录
├─ ├─ bug/                  # BUG记录
├─ └─ sql/                  # 数据库表设计方案、SQL-DDL文件
├─ deploy                   # 系统启动与部署手册
├─ tests/                   # 测试开发模块
├─ config.example.yaml      # Template → copy to config.yaml (gitignored) at repo root
├── extensions_config.json  # MCP servers and skills configuration
└─ README.md                # 项目手册, 先强制为空文档.
```

## 开发规范

1. **任务顺序：分析需求 -> 需求分析通过 -> git 新分支 -> 开发 -> 测试 -> review -> debugger -> 测试 -> ... -> 测试通过 -> 合并 git 分支.**

2. **开发文档规范：所有文档写在 `docs/*`, 例如：`docs/plan`、`docs/review`、`docs/bug`.**

3. 计划文档规范：在`docs/plan`创建需求开发文档, 先划分大步骤（1、2、...）, 再划分子步骤（1.1、1.2、...）, 打上 `- [ ]` 标记；每完成一步, 则打上 `- [X]`.


## Git 规范

- Git提交信息使用规范前缀：`feat|fix|docs|refactor|test|chore|build|ci|...`, 必须使用括号写出代码修改总体位置, 总体分三大类: `backend-xxx` 、`agent-xxx` 、`frontend-xxx`,例如: `feat(backend-api): xxx`

- Git提交备注要采用中文, 提交信息必须有开发摘要(修复哪些问题+修改位置), 方便后续查阅.

- `main` 是稳定主分支；新功能/修改 BUG 必须从 `main` 新建`feat|fix|...`分支.

- 禁止使用 `codex/xx` | `claude/xxx` 的前缀创建和提交分支名称.

- `feat|fix|...`分支开发测试完成后, 必须及时合并回本地 `main` 并删除分支, 避免多分支长期存在导致重复开发、重复冲突和分支列表累积过深.

- 远程 `main` 推送必须设置严格：只有本地功能分支已经完整合并到 `main`、测试 / 检查无异常、工作区干净并确认本地 `main` 状态正确时, 才能推送到远程 `main` 分支.

- 如果本地功能分支尚未完全合并、测试未通过、工作区不干净、存在冲突或状态不确定, 禁止推送远程 `main`；此时如确实需要远程同步, 只能推送当前功能分支到远程.

## Where to Go Next

- Backend work → **[backend/AGENTS.md](backend/AGENTS.md)**
- Frontend work → **[frontend/AGENTS.md](frontend/AGENTS.md)**
- test work → **[tests/AGENTS.md](tests/AGENTS.md)**
- Setup & install → **[deploy/Install.md](deploy/Install.md)**

## Cross-Cutting Conventions

These apply repo-wide; module guides own the module-specific detail.

- **文档编写**: 必须使用简体中文编写文档.
- **Documentation update policy** — keep docs in sync with code: update the relevant `AGENTS.md` for development/architecture changes in
  the same change set.
- **Test-driven development** — features and bug fixes ship with tests. Backend tests live
  in `backend/tests/` (TDD is mandatory there; see [backend/AGENTS.md](backend/AGENTS.md));
  frontend tests live in `frontend/tests/`.

## 生产部署与访问边界

- 公网正式环境使用宝塔宿主机 Nginx 终止 HTTPS 和反向代理，Docker Compose
  不启动第二个 Nginx，也不允许 PostgreSQL、Redis 对公网发布端口。
- 前端通过当前域名访问 `/api`、`/api/sse` 和 `/api/ws`；禁止在生产代码、
  配置或文档中写死 `localhost:8000`、宿主机后端端口或容器服务名。
- 宝塔 Nginx 必须保留 SSE 的 `proxy_buffering off` 和 WebSocket 的
  `Upgrade`/`Connection` 转发，修改前端传输路径时必须同步检查
  `deploy/baota-reverse-proxy.conf`。
- 部署环境变量和生产配置只保存在服务器，不得提交 Git；生产环境禁止执行
  `seed_demo` 或使用演示账号密码。
- 生产 Compose 使用已构建的版本化镜像，不在服务器执行源码构建；应用镜像必须
  与 `.env.production` 中的 `IMAGE_TAG` 完全一致。
- 前端镜像构建时必须传入最终 HTTPS `PUBLIC_ORIGIN`，域名变化需要重新构建前端
  镜像；服务器只上传镜像发布包、Compose 文件和运行时配置。
- 如需复现本机演示状态，只能使用 `deploy/export-demo-data.ps1` 导出
  PostgreSQL 与 `backend/storage`，并在确认是演示服务器后执行
  `DEMO_RESTORE_CONFIRM=YES ./deploy.sh demo-restore`；该操作会覆盖目标数据库。
- 真实数据包可能包含身份证、手机号、对话、签名和音频，禁止提交 Git、放入
  Web 可公开目录或长期保留服务器临时目录；Redis 登录会话、SSE 游标和 Celery
  队列不迁移，服务器使用新 Redis 数据卷。
- 浏览器只能访问已启动的 HTTPS 站点，不能执行 Docker 或替代服务器部署命令；
  修改生产端口时必须同步更新 `.env.production` 与 `deploy/baota-reverse-proxy.conf`。
