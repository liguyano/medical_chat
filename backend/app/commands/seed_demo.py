"""一键导入第一期演示数据
作用：幂等准备患者身份、住院记录、已发布量表和关键词规则。
用法：在 backend 目录执行 `uv run python -m app.commands.seed_demo`。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.configs.app_config import get_app_config
from app.managers.assessment_catalog_importer import AssessmentCatalogImporter
from app.managers.interaction_rule_importer import InteractionRuleImporter
from app.managers.patient_seeder import PatientSeeder
from app.models.base import init_db


def main() -> None:
    """初始化数据库并幂等导入演示数据。"""
    parser = argparse.ArgumentParser(description="导入演示患者、量表和关键词规则")
    parser.add_argument(
        "--scales-directory",
        type=Path,
        default=Path(__file__).resolve().parents[3]
        / "docs"
        / "structured"
        / "assessment-scales",
    )
    parser.add_argument(
        "--skip-scales",
        action="store_true",
        help="跳过量表导入",
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

    result: dict[str, object] = {"patients": PatientSeeder().seed()}
    if not args.skip_scales:
        result["scales"] = AssessmentCatalogImporter().import_directory(
            args.scales_directory,
            publish_status="已发布",
        )
    result["rules"] = InteractionRuleImporter().import_from_file()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
