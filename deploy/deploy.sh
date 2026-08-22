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
  up         使用已加载镜像启动全部服务
  update     使用新镜像标签重建应用服务
  images     检查当前版本应用镜像
  down       停止并移除容器（不删除数据卷）
  ps         查看服务状态
  logs       查看全部服务日志
  bootstrap  导入生产量表/规则并创建首个医护账号
  config     校验 Compose 配置
EOF
}

require_application_images() {
    local missing=0
    while IFS= read -r image; do
        [[ -z "${image}" ]] && continue
        if ! docker image inspect "${image}" >/dev/null 2>&1; then
            echo "缺少应用镜像：${image}" >&2
            missing=1
        fi
    done < <("${COMPOSE[@]}" config --images | grep '^medical-evaluate-' | sort -u)

    if [[ "${missing}" -ne 0 ]]; then
        echo "请先在服务器执行 docker load 导入本次发布镜像包。" >&2
        exit 1
    fi
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
        require_application_images
        "${COMPOSE[@]}" up -d --no-build --remove-orphans
        "${COMPOSE[@]}" ps
        ;;
    update)
        require_files
        "${COMPOSE[@]}" config --quiet
        require_application_images
        "${COMPOSE[@]}" up -d --no-build --force-recreate --remove-orphans
        "${COMPOSE[@]}" ps
        ;;
    images)
        require_files
        "${COMPOSE[@]}" config --images | grep '^medical-evaluate-' | sort -u
        require_application_images
        echo "应用镜像检查通过。"
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
        require_application_images
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
