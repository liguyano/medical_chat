# 修复前端生产镜像 standalone 依赖部署计划

## 需求目标

修复本机完整 Compose 验证中前端容器因缺少
`@swc/helpers/esm/_interop_require_default.js` 反复重启的问题，确保生产
standalone 镜像能正常提供 Next.js 页面。

## 开发步骤

### 1. 原因确认

- [X] 1.1 在隔离 Compose 中验证后端、数据库、Redis、Worker 和 API。
- [X] 1.2 检查前端容器日志，确认 standalone 输出中的 pnpm 依赖缺少 SWC ESM 文件。

### 2. 镜像修复

- [X] 2.1 将 `@swc/helpers` 的完整运行时目录复制到 standalone 镜像。
- [X] 2.2 保持非 root 运行和现有 Next.js standalone 启动方式。

### 3. 验证与交付

- [X] 3.1 重新构建前端镜像并验证容器稳定运行。
- [X] 3.2 验证前端 HTTP、后端健康检查和完整 Compose 状态。
- [X] 3.3 更新审查文档和安装手册。
- [X] 3.4 提交功能分支并合并本地 `main`。

### 4. 共享存储卷初始化

- [X] 4.1 在完整 Compose 验证中发现空应用存储卷的并发挂载竞争。
- [X] 4.2 增加一次性 `storage-init` 服务，让 API、Worker 和 Beat 等待卷初始化完成。
