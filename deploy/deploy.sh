#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

COMPOSE=(docker compose --env-file .env.production -f docker-compose.yaml)

require_files() {
    [[ -f .env.production ]] || {
        echo "缺少 deploy/.env.production，请先复制 .env.production.example 并填写密钥。" >&2
        exit 1
    }
    [[ -f config.production.yaml ]] || {
        echo "缺少 deploy/config.production.yaml，请先复制 config.production.example.yaml。" >&2
        exit 1
    }
}

usage() {
    cat <<'EOF'
用法：./deploy.sh <命令>

命令：
  up         构建镜像并启动全部服务
  update     重新构建并滚动重建应用服务
  down       停止并移除容器（不删除数据卷）
  ps         查看服务状态
  logs       查看全部服务日志
  bootstrap  导入生产量表/规则并创建首个医护账号
  config     校验 Compose 配置
EOF
}

command="${1:-}"
case "${command}" in
    config)
        require_files
        "${COMPOSE[@]}" config --quiet
        echo "Compose 配置校验通过。"
        ;;
    up)
        require_files
        "${COMPOSE[@]}" config --quiet
        "${COMPOSE[@]}" up -d --build
        "${COMPOSE[@]}" ps
        ;;
    update)
        require_files
        "${COMPOSE[@]}" config --quiet
        "${COMPOSE[@]}" up -d --build --remove-orphans
        "${COMPOSE[@]}" ps
        ;;
    down)
        require_files
        "${COMPOSE[@]}" down --remove-orphans
        ;;
    ps)
        require_files
        "${COMPOSE[@]}" ps
        ;;
    logs)
        require_files
        "${COMPOSE[@]}" logs -f --tail=200
        ;;
    bootstrap)
        require_files
        : "${BOOTSTRAP_STAFF_NO:?请设置 BOOTSTRAP_STAFF_NO}"
        : "${BOOTSTRAP_STAFF_NAME:?请设置 BOOTSTRAP_STAFF_NAME}"
        : "${BOOTSTRAP_STAFF_PASSWORD:?请设置 BOOTSTRAP_STAFF_PASSWORD}"
        "${COMPOSE[@]}" run --rm --no-deps \
            -e BOOTSTRAP_STAFF_NO \
            -e BOOTSTRAP_STAFF_NAME \
            -e BOOTSTRAP_STAFF_PASSWORD \
            -e BOOTSTRAP_STAFF_ROLE \
            -e BOOTSTRAP_STAFF_DEPARTMENT \
            -e BOOTSTRAP_ROTATE_PASSWORD \
            api python -m app.commands.bootstrap_production
        ;;
    *)
        usage
        exit 2
        ;;
esac
