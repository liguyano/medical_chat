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

## Step1

## ...