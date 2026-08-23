# 公网宝塔 Docker 部署代码审查

## 审查范围

- `deploy/docker-compose.yaml`
- 后端和前端生产 Dockerfile
- 宝塔 Nginx 反向代理片段
- Alembic 容器配置读取
- 生产初始化和签名文件访问
- `deploy/Install.md` 及各级 `AGENTS.md`
- 本地镜像构建、导出和服务器无源码启动流程
- 真实 PostgreSQL、应用存储和 Redis 恢复流程

## 已验证

- Compose 配置校验通过。
- `deploy/deploy.sh` Bash 语法校验通过。
- 后端 `tests/unit-test`：233 个测试通过。
- 前端 Vitest：22 个测试文件、66 个测试通过。
- 前端 ESLint、TypeScript 检查和 Next.js standalone 生产构建通过。
- Alembic 可读取 `APP_DATABASE__HOST`、`APP_DATABASE__PORT` 生成容器数据库连接串。
- 本地任务结束前已停止监听 3000/8000 的前后端进程。
- `docker-compose.yaml` 已移除生产构建上下文，只引用版本化应用镜像。
- `deploy/build-images.ps1` PowerShell 语法校验通过，可构建指定平台的后端、
  前端镜像并导出发布包。
- `deploy.sh` 已使用 `--no-build` 启动，并在启动前检查应用镜像是否已 `docker load`。
- `.gitattributes` 已强制 Shell、Compose 和 Nginx 配置使用 Linux 兼容换行符。
- 已验证 Windows PowerShell 5.1 可解析 `build-images.ps1`；发布包中的
  `deploy.sh` 会被统一转换为无 BOM 的 LF 换行。
- 已增加 `export-demo-data.ps1`，以 PostgreSQL custom dump 和
  `backend/storage` tar.gz 导出真实演示数据，并为每个文件生成
  `hash  filename` 格式的 SHA256 校验文件。
- 已增加 `restore-demo-data.sh` 与 `deploy.sh demo-restore`。恢复前必须显式设置
  `DEMO_RESTORE_CONFIRM=YES`；脚本会清理目标 PostgreSQL 对象、恢复音频/签名，
  删除旧 Redis 运行态并重新创建空 Redis 数据卷，然后执行迁移并启动完整服务。
- 已更新根目录、后端和前端 `AGENTS.md`，明确真实数据包不得提交 Git 或放入公开目录，
  Redis 不迁移，浏览器不能执行 Docker，且生产端口变更必须同步宝塔 Nginx。

## 未完成的运行时验证

本机 Docker 构建两次因连接 Docker Hub 基础镜像仓库失败而中断，未能完成
Linux 容器实际启动、HTTP、SSE、WebSocket 和 HTTPS 联调。部署服务器首次执行
本地执行 `build-images.ps1` 时需要确保 Docker Hub、PyPI 和 npm/pnpm 网络可用，
或提前配置镜像加速/私有镜像仓库。服务器仅在未提前导入 PostgreSQL/Redis 镜像时
需要访问 Docker Hub。

## 风险与后续建议

- 正式环境必须先在宝塔申请并验证 Let’s Encrypt 证书，再合并 Nginx 片段。
- 应在真实服务器上验证证书续期后的 Nginx reload、SSE 长连接和 WebSocket 语音。
- 应配置 PostgreSQL、应用存储和 Redis 的异地备份，并进行恢复演练。
- 当前仅完成脚本级静态验证，未在隔离临时数据库/卷上实际执行真实数据恢复；
  首次上线前应先制作脱敏副本进行完整恢复演练，再处理正式数据包。
