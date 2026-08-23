# 修复后端生产镜像缺少 medagent 部署计划

## 需求目标

修复生产后端 Docker 镜像在执行 Alembic 迁移时出现
`ModuleNotFoundError: No module named 'medagent'` 的问题，重新构建可在服务器
执行 `demo-restore` 的后端镜像。

## 开发步骤

### 1. 原因确认

- [X] 1.1 检查后端 Dockerfile 的 uv 安装参数。
- [X] 1.2 确认 `backend/packages/medagent` 是项目源码包且未被镜像运行环境导入。

### 2. 镜像修复

- [X] 2.1 在复制完整后端源码后安装项目本身，确保 `medagent` 进入生产虚拟环境。
- [X] 2.2 保留非 root 运行、生产依赖锁定和现有存储目录权限设置。

### 3. 验证与发布

- [X] 3.1 校验 Dockerfile、Compose 和脚本语法。
- [X] 3.2 本地构建并验证镜像内可导入 `medagent`。
- [X] 3.3 更新部署审查和安装手册，说明数据包无需重新导出。
- [ ] 3.4 提交功能分支并合并本地 `main`。
