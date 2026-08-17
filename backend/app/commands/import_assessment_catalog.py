"""导入结构化量表目录
用法：在 backend 目录执行 `uv run python -m app.commands.import_assessment_catalog`。
"""

import argparse
import json
from pathlib import Path

from app.configs.app_config import get_app_config
from app.managers.assessment_catalog_importer import AssessmentCatalogImporter
from app.models.base import init_db


def main() -> None:
    """初始化数据库并幂等导入真实量表。"""
    parser = argparse.ArgumentParser(description="导入 docs/structured 量表目录")
    parser.add_argument(
        "--directory",
        type=Path,
        default=Path(__file__).resolve().parents[3]
        / "docs"
        / "structured"
        / "assessment-scales",
    )
    parser.add_argument(
        "--publish-status",
        choices=["草稿", "审核中", "已发布", "已停用"],
        default=None,
        help="覆盖源文件状态；临床审核完成前禁止使用“已发布”",
    )
    args = parser.parse_args()

    config = get_app_config()
    init_db(
        config.database.url,
        pool_size=config.database.pool_size,
        max_overflow=config.database.max_overflow,
        pool_pre_ping=config.database.pool_pre_ping,
        echo=config.database.echo,
    )
    counters = AssessmentCatalogImporter().import_directory(
        args.directory,
        publish_status=args.publish_status,
    )
    print(json.dumps(counters, ensure_ascii=False))


if __name__ == "__main__":
    main()
