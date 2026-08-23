#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

COMPOSE=(docker compose --env-file .env.production -f docker-compose.yaml)
PROJECT_NAME="medical-evaluate"
STORAGE_VOLUME="${PROJECT_NAME}_medical_evaluate_app_storage"

require_files() {
    [[ -f .env.production ]] || {
        echo "缺少 .env.production。" >&2
        exit 1
    }
    [[ -f config.production.yaml ]] || {
        echo "缺少 config.production.yaml。" >&2
        exit 1
    }
}

require_confirmation() {
    [[ "${DEMO_RESTORE_CONFIRM:-}" == "YES" ]] || {
        echo "真实数据恢复是破坏性操作。" >&2
        echo "确认目标是演示环境后，先执行：export DEMO_RESTORE_CONFIRM=YES" >&2
        exit 1
    }
}

find_data_file() {
    local pattern="$1"
    find . -maxdepth 1 -type f -name "$pattern" -print -quit
}

wait_for_postgres() {
    local attempt
    for attempt in $(seq 1 60); do
        if "${COMPOSE[@]}" exec -T postgres pg_isready \
            -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
    done
    echo "PostgreSQL 在规定时间内未就绪。" >&2
    exit 1
}

require_files
require_confirmation

set -a
# .env.production 只允许使用简单 KEY=VALUE 配置，密钥不要包含未转义空格。
# shellcheck disable=SC1091
source ./.env.production
set +a

POSTGRES_DUMP="$(find_data_file 'medical-evaluate-demo-postgres-*.dump')"
STORAGE_ARCHIVE="$(find_data_file 'medical-evaluate-demo-storage-*.tar.gz')"

[[ -n "${POSTGRES_DUMP}" ]] || {
    echo "当前目录未找到 PostgreSQL 演示备份。" >&2
    exit 1
}
[[ -n "${STORAGE_ARCHIVE}" ]] || {
    echo "当前目录未找到应用存储演示归档。" >&2
    exit 1
}

if [[ -f "${POSTGRES_DUMP}.sha256" ]]; then
    sha256sum -c "${POSTGRES_DUMP}.sha256"
fi
if [[ -f "${STORAGE_ARCHIVE}.sha256" ]]; then
    sha256sum -c "${STORAGE_ARCHIVE}.sha256"
fi

echo "停止应用服务，保留数据库和 Redis 容器。"
"${COMPOSE[@]}" stop api frontend worker-dialog worker-schedule \
    worker-extraction celery-beat >/dev/null 2>&1 || true

echo "清理 Redis 运行态，恢复后使用全新 Redis 数据卷。"
"${COMPOSE[@]}" stop redis-app redis-celery >/dev/null 2>&1 || true
"${COMPOSE[@]}" rm -f redis-app redis-celery >/dev/null 2>&1 || true
docker volume rm \
    "${PROJECT_NAME}_medical_evaluate_redis_app_data" \
    "${PROJECT_NAME}_medical_evaluate_redis_celery_data" \
    >/dev/null 2>&1 || true

echo "启动 PostgreSQL。"
"${COMPOSE[@]}" up -d postgres
wait_for_postgres

echo "恢复 PostgreSQL 数据库：${POSTGRES_DUMP}"
"${COMPOSE[@]}" exec -T \
    -e "PGPASSWORD=${POSTGRES_PASSWORD}" \
    postgres pg_restore \
    --username="${POSTGRES_USER}" \
    --dbname="${POSTGRES_DB}" \
    --clean \
    --if-exists \
    --no-owner \
    --no-privileges \
    < "${POSTGRES_DUMP}"

echo "创建应用存储卷：${STORAGE_VOLUME}"
docker volume create "${STORAGE_VOLUME}" >/dev/null

echo "恢复音频和签名文件：${STORAGE_ARCHIVE}"
docker run --rm \
    --user 0:0 \
    -v "${STORAGE_VOLUME}:/target" \
    -v "$(pwd)/${STORAGE_ARCHIVE#./}:/backup/storage.tar.gz:ro" \
    alpine:3.20 \
    sh -ec 'find /target -mindepth 1 -maxdepth 1 -exec rm -rf {} +; tar -xzf /backup/storage.tar.gz -C /target'

echo "执行数据库迁移兼容检查。"
"${COMPOSE[@]}" run --rm migrate

echo "启动全部应用服务。"
"${COMPOSE[@]}" up -d --no-build --remove-orphans

echo "真实数据演示恢复完成。"
