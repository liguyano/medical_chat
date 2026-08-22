# 公网宝塔 Docker 部署代码审查

## 审查范围

- `deploy/docker-compose.yaml`
- 后端和前端生产 Dockerfile
- 宝塔 Nginx 反向代理片段
- Alembic 容器配置读取
- 生产初始化和签名文件访问
- `deploy/Install.md` 及各级 `AGENTS.md`

## 已验证

- Compose 配置校验通过。
- `deploy/deploy.sh` Bash 语法校验通过。
- 后端 `tests/unit-test`：233 个测试通过。
- 前端 Vitest：22 个测试文件、66 个测试通过。
- 前端 ESLint、TypeScript 检查和 Next.js standalone 生产构建通过。
- Alembic 可读取 `APP_DATABASE__HOST`、`APP_DATABASE__PORT` 生成容器数据库连接串。
- 本地任务结束前已停止监听 3000/8000 的前后端进程。

## 未完成的运行时验证

本机 Docker 构建两次因连接 Docker Hub 基础镜像仓库失败而中断，未能完成
Linux 容器实际启动、HTTP、SSE、WebSocket 和 HTTPS 联调。部署服务器首次执行
`./deploy.sh up` 时需要确保 Docker Hub 网络可用，或提前配置镜像加速/私有镜像仓库。

## 风险与后续建议

- 正式环境必须先在宝塔申请并验证 Let’s Encrypt 证书，再合并 Nginx 片段。
- 应在真实服务器上验证证书续期后的 Nginx reload、SSE 长连接和 WebSocket 语音。
- 应配置 PostgreSQL、应用存储和 Redis 的异地备份，并进行恢复演练。
