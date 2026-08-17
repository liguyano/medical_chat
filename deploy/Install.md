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

## Step1

## ...


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

```powershell
pnpm build
pnpm start
```

浏览器访问：

- 医护端：`http://localhost:3000/nurse`
- 患者端：`http://localhost:3000/patient`
