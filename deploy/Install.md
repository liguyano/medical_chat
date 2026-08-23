# Install.md
本文档记录系统启动的完整部署/启动指南，用户可按照本文档步骤启动项目。
公网正式环境使用本地构建 Docker 镜像、上传服务器后启动的方式。
> 公网正式环境请先阅读第 0 节；第 1 节及之后保留为本地开发联调指南。

# 0. Linux 公网正式部署（宝塔 + Docker）

本节用于生产环境。宝塔宿主机 Nginx 负责域名、HTTPS 和反向代理；
Docker Compose 负责前端、后端、PostgreSQL、Redis、Celery Worker 和 Beat。
宝塔 Nginx 不与 Compose 重复启动，避免争抢 `80/443` 端口。

## 0.1 服务器准备

服务器需要安装：

- Linux（推荐 Ubuntu 22.04/24.04）
- Docker Engine 和 Docker Compose v2
- 宝塔面板及 Nginx
- `curl`

在云服务器安全组和宝塔防火墙中只开放：

```text
22/tcp   SSH（建议限制来源 IP）
80/tcp   HTTP（用于证书签发和跳转 HTTPS）
443/tcp  HTTPS
```

PostgreSQL、Redis、前端和后端端口不应对公网开放。

## 0.2 域名和宝塔证书

1. 将域名 `A` 记录指向服务器公网 IP。
2. 在宝塔中创建站点，例如 `app.example.com`。
3. 在站点的“SSL”中申请 Let’s Encrypt 证书。
4. 开启“强制 HTTPS”。
5. 将本目录的 `baota-reverse-proxy.conf` 内容合并到该站点的
   HTTPS `server { ... }` 配置中，然后保存并重载 Nginx。

配置中使用两个本机端口：

```text
前端：127.0.0.1:13000
后端：127.0.0.1:18000
```

端口可以修改，不需要重新构建镜像：在服务器 `.env.production` 中修改
`FRONTEND_BIND_PORT`、`API_BIND_PORT`，并将本文件中的宝塔 Nginx
`proxy_pass` 端口同步改成相同值，然后测试并重载 Nginx。数据库和 Redis
容器端口不要发布到宿主机或公网。

SSE 和 WebSocket 的代理配置不能省略，否则实时对话和语音功能会断开。

## 0.3 本地构建 Linux 镜像

本项目生产部署采用“本地构建、服务器导入”的方式。服务器不需要
`backend`、`frontend` 源码，也不需要在服务器上安装 Python、Node.js、uv 或 pnpm。

本地 Windows 电脑需要：

- Docker Desktop，使用 Linux containers；
- Docker Buildx；
- 能够访问 Docker Hub、PyPI 和 npm/pnpm 镜像源；
- 当前项目源代码。

在项目根目录打开 PowerShell，执行：

```powershell
Set-Location D:\A-AICodeWork\medical-evaluate

.\deploy\build-images.ps1 `
  -PublicOrigin "https://app.example.com" `
  -ReleaseTag "20260822-01" `
  -Platform "linux/amd64"
```

说明：

- `PublicOrigin` 必须是最终宝塔站点的 HTTPS 地址，不能带结尾 `/`；
- `ReleaseTag` 是本次发布版本号，建议使用日期和序号；
- 常见 x86_64 服务器使用 `linux/amd64`；
- ARM 服务器改用 `linux/arm64`；
- 前端域名写入 Next.js 构建产物，域名变更后必须重新构建前端镜像。

脚本完成后，会生成：

```text
release/20260822-01/
├─ medical-evaluate-images-20260822-01.tar
├─ medical-evaluate-images-20260822-01.tar.sha256
├─ docker-compose.yaml
├─ deploy.sh
├─ baota-reverse-proxy.conf
├─ .env.production.example
├─ config.production.example.yaml
└─ RELEASE.txt
```

镜像包中不包含生产密码和模型密钥。

如果服务器可以访问 Docker Hub，只需传输本次项目的两个镜像；
PostgreSQL 和 Redis 会在服务器启动时自动拉取。若服务器没有外网，
本地还需要执行以下命令，把中间件镜像一并导出：

```powershell
docker pull postgres:16-alpine
docker pull redis:7-alpine

docker save `
  medical-evaluate-backend:20260822-01 `
  medical-evaluate-frontend:20260822-01 `
  postgres:16-alpine `
  redis:7-alpine `
  -o .\release\20260822-01\medical-evaluate-images-all-20260822-01.tar

$imageHash = (Get-FileHash `
  .\release\20260822-01\medical-evaluate-images-all-20260822-01.tar `
  -Algorithm SHA256).Hash.ToLowerInvariant()
$ascii = New-Object System.Text.ASCIIEncoding
[System.IO.File]::WriteAllText(
  '.\release\20260822-01\medical-evaluate-images-all-20260822-01.tar.sha256',
  "$imageHash  medical-evaluate-images-all-20260822-01.tar`n",
  $ascii
)
```

## 0.4 导出真实演示数据

镜像构建完成后，在本地停止 FastAPI、Next.js、Celery Worker 和 Beat，
避免数据库与文件同时写入。然后执行：

```powershell
Set-Location D:\A-AICodeWork\medical-evaluate

.\deploy\export-demo-data.ps1 `
  -ReleaseDirectory ".\release\20260822-01" `
  -PostgresContainer "medical-evaluate-postgres" `
  -PostgresUser "medical" `
  -Database "medical_evaluate"
```

脚本会导出：

```text
medical-evaluate-demo-postgres-20260822-01.dump
medical-evaluate-demo-postgres-20260822-01.dump.sha256
medical-evaluate-demo-storage-20260822-01.tar.gz
medical-evaluate-demo-storage-20260822-01.tar.gz.sha256
DEMO-DATA.txt
```

数据包包含当前 PostgreSQL 数据、知情同意签名、对话音频等真实数据。
Redis 登录会话、SSE 游标和 Celery 临时队列不会导出。

导出后建议检查文件大小：

```powershell
Get-ChildItem .\release\20260822-01\medical-evaluate-demo-*
```

## 0.5 上传发布包到服务器

建议上传到服务器的临时目录，不要直接覆盖正在运行的部署目录。
PowerShell 通过 `scp` 上传示例：

```powershell
scp -r `
  .\release\20260822-01 `
  root@服务器公网IP:/opt/medical-evaluate-release/
```

上传内容至少包括：

```text
medical-evaluate-images-20260822-01.tar
medical-evaluate-images-20260822-01.tar.sha256
medical-evaluate-demo-postgres-20260822-01.dump
medical-evaluate-demo-postgres-20260822-01.dump.sha256
medical-evaluate-demo-storage-20260822-01.tar.gz
medical-evaluate-demo-storage-20260822-01.tar.gz.sha256
DEMO-DATA.txt
docker-compose.yaml
deploy.sh
restore-demo-data.sh
baota-reverse-proxy.conf
.env.production.example
config.production.example.yaml
```

## 0.6 服务器导入镜像并准备配置

SSH 登录服务器后执行：

```bash
mkdir -p /opt/medical-evaluate/deploy
cd /opt/medical-evaluate-release/20260822-01

sha256sum -c medical-evaluate-images-20260822-01.tar.sha256

docker load -i medical-evaluate-images-20260822-01.tar
```

如果导出的是包含中间件的镜像包，则改为：

```bash
sha256sum -c medical-evaluate-images-all-20260822-01.tar.sha256
docker load -i medical-evaluate-images-all-20260822-01.tar
```

复制运行文件：

```bash
cp docker-compose.yaml deploy.sh baota-reverse-proxy.conf \
  /opt/medical-evaluate/deploy/
cp restore-demo-data.sh \
  /opt/medical-evaluate/deploy/
cp .env.production.example config.production.example.yaml \
  /opt/medical-evaluate/deploy/
cp medical-evaluate-demo-* DEMO-DATA.txt \
  /opt/medical-evaluate/deploy/

cd /opt/medical-evaluate/deploy
chmod 700 deploy.sh restore-demo-data.sh
cp .env.production.example .env.production
cp config.production.example.yaml config.production.yaml
chmod 600 .env.production
# 后端容器以 UID 10001 的非 root 用户读取该文件。
chown 10001:10001 config.production.yaml
chmod 600 config.production.yaml
```

编辑 `.env.production`，至少修改：

```dotenv
PUBLIC_ORIGIN=https://app.example.com
IMAGE_TAG=20260822-01
POSTGRES_PASSWORD=随机强密码
REDIS_APP_PASSWORD=随机强密码
REDIS_CELERY_PASSWORD=随机强密码
PATIENT_IDENTITY_SECRET=随机长密钥
DASHSCOPE_API_KEY=真实模型密钥
```

编辑 `config.production.yaml`，确认语音模型中的 `{WorkspaceId}` 已替换为
真实工作空间 ID。禁止提交 `.env.production` 和 `config.production.yaml`。
如果修改配置文件后编辑器将所有权恢复为 root，请再次执行：

```bash
chown 10001:10001 config.production.yaml
chmod 600 config.production.yaml
```

`IMAGE_TAG` 必须与本次导入的镜像标签完全一致。若写成 `latest`，
服务器必须实际加载带有 `:latest` 标签的镜像。

## 0.7 恢复真实数据并启动容器

这是破坏性恢复操作，只能用于空白演示服务器或明确允许覆盖的演示环境。
确认目标服务器无须保留现有数据库后执行：

```bash
export DEMO_RESTORE_CONFIRM=YES
./deploy.sh demo-restore
unset DEMO_RESTORE_CONFIRM
```

恢复脚本会：

1. 停止 API、前端和 Worker；
2. 启动 PostgreSQL；
3. 校验并恢复 PostgreSQL 数据；
4. 恢复音频和签名到应用存储卷；
5. 执行迁移兼容检查；
6. 使用空 Redis 数据卷启动完整系统。

恢复完成后，不要执行 `./deploy.sh bootstrap`，因为医护账号和患者数据已经
从演示数据库恢复。

如果只部署空数据库、不恢复本机数据，才执行普通启动：

首次启动前先校验 Compose 配置：

```bash
./deploy.sh config
```

服务器不重新构建镜像，执行数据库迁移并启动全部服务：

```bash
./deploy.sh up
```

如果不使用脚本，也可以直接输入 Docker Compose 命令：

```bash
docker compose \
  --env-file .env.production \
  -f docker-compose.yaml \
  config --quiet

docker compose \
  --env-file .env.production \
  -f docker-compose.yaml \
  up -d --no-build --remove-orphans
```

查看状态和日志：

```bash
./deploy.sh images
./deploy.sh ps
./deploy.sh logs
```

等价的 Docker 命令：

```bash
docker compose --env-file .env.production -f docker-compose.yaml ps
docker compose --env-file .env.production -f docker-compose.yaml logs -f --tail=200
```

首次生产初始化不会导入演示患者和演示密码。需要显式创建首个医护账号，
例如：

```bash
export BOOTSTRAP_STAFF_NO=ADMIN001
export BOOTSTRAP_STAFF_NAME="系统护士"
export BOOTSTRAP_STAFF_PASSWORD="至少12位的强密码"
export BOOTSTRAP_STAFF_ROLE=nurse
export BOOTSTRAP_STAFF_DEPARTMENT="护理部"
./deploy.sh bootstrap
unset BOOTSTRAP_STAFF_NO BOOTSTRAP_STAFF_NAME BOOTSTRAP_STAFF_PASSWORD
unset BOOTSTRAP_STAFF_ROLE BOOTSTRAP_STAFF_DEPARTMENT
```

`bootstrap` 会导入正式量表和交互规则，但不会创建演示患者。

## 0.8 部署验证

```bash
curl -I https://app.example.com
curl -fsS https://app.example.com/health
docker compose --env-file .env.production -f docker-compose.yaml ps
```

浏览器访问：

- 医护端：`https://app.example.com/nurse`
- 患者端：`https://app.example.com/patient`

确认浏览器开发者工具中 API、SSE 和 WebSocket 均使用当前 HTTPS 域名，
不能出现 `localhost:8000`。

## 0.9 更新、回滚和停止

发布新版本时，在本地使用新的 `ReleaseTag` 构建镜像并上传新发布目录。
服务器执行：

```bash
cd /opt/medical-evaluate-release/20260822-02
sha256sum -c medical-evaluate-images-20260822-02.tar.sha256
docker load -i medical-evaluate-images-20260822-02.tar

cd /opt/medical-evaluate/deploy
cp /opt/medical-evaluate-release/20260822-02/docker-compose.yaml .
cp /opt/medical-evaluate-release/20260822-02/deploy.sh .
cp /opt/medical-evaluate-release/20260822-02/baota-reverse-proxy.conf .
sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=20260822-02/' .env.production
./deploy.sh update
```

`update` 使用 `--no-build`，只使用已经通过 `docker load` 导入的新镜像。

回滚时把 `IMAGE_TAG` 改回旧版本，再执行：

```bash
sed -i 's/^IMAGE_TAG=.*/IMAGE_TAG=20260822-01/' .env.production
./deploy.sh update
```

停止应用但保留数据库和 Redis 数据卷：

```bash
./deploy.sh down
```

禁止执行 `docker compose down -v`，除非确认要删除全部数据。

## 0.10 数据备份

至少定期备份：

- PostgreSQL 数据库；
- `medical_evaluate_app_storage` 中的音频和签名；
- Compose 环境文件和生产配置（保存到受控密钥存储，不要提交 Git）。

PostgreSQL 示例：

```bash
docker compose --env-file .env.production -f docker-compose.yaml exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backup-$(date +%F).sql
```

备份文件必须存放到服务器之外，并定期验证可恢复性。

## 0.11 生产安全要求

- 禁止执行 `seed_demo`，禁止使用 `123456`。
- 只开放 SSH、HTTP、HTTPS，数据库和 Redis 仅在 Docker 内部网络通信。
- 定期更新宝塔、Nginx、Docker 基础镜像和系统安全补丁。
- `PATIENT_IDENTITY_SECRET`、数据库密码、Redis 密码和模型 API Key 必须使用随机
  密钥，并限制文件权限。
- 签名和音频使用 Docker 数据卷持久化，不能依赖容器临时文件系统。

## 0.12 常见恢复错误

如果 `./deploy.sh demo-restore` 在迁移阶段出现：

```text
ModuleNotFoundError: No module named 'medagent'
```

说明服务器导入的是旧后端镜像。`backend.Dockerfile` 已要求在复制完整源码后
安装项目本身；请使用修复后的新版本重新构建并导入镜像。数据库和存储数据包
无需重新导出。

服务器导入新镜像后，确认 `.env.production` 的 `IMAGE_TAG` 已改为新标签，再执行：

```bash
docker load -i medical-evaluate-images-新版本.tar
./deploy.sh demo-restore
```

如果首次空库启动时看到应用存储卷目录创建冲突，说明使用了旧版 Compose。
请更新 `docker-compose.yaml`，确保包含 `storage-init` 服务；新版 Compose 会先
初始化 `consent-signatures`、`dialog-audio` 目录，再启动 API、Worker 和 Beat。

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

`config.yaml` 中四个 Agent 必须绑定测试语言模型：

```yaml
agent_models:
  dialog_agent:
    language: qwen3.5-flash
  schedule_agent:
    language: qwen3.5-flash
  extraction_agent:
    language: qwen3.5-flash
  nursing_plan_agent:
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
