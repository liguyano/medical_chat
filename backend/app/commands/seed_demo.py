"""一键导入第一期演示数据
作用：幂等准备文本对话闭环体验所需的全部种子数据——
      1) 5 位医护账号；
      2) 10 位在院患者及住院记录；
      3) 5 张真实量表（导入并发布为“已发布”版本，供加载器读取）；
      4) 关键词交互规则（抽烟/喝酒/过敏等，触发追问约束）。
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
from app.managers.staff_seeder import StaffSeeder
from app.models.base import init_db


def main() -> None:
    """初始化数据库并幂等导入演示患者、量表与关键词规则。"""
    parser = argparse.ArgumentParser(
        description="导入第一期演示数据（医护/患者/量表/关键词规则）"
    )
    parser.add_argument(
        "--scales-directory",
        type=Path,
        default=Path(__file__).resolve().parents[3]
        / "docs"
        / "structured"
        / "assessment-scales",
        help="结构化量表目录",
    )
    parser.add_argument(
        "--publish-status",
        choices=["草稿", "审核中", "已发布", "已停用"],
        default="已发布",
        help="覆盖量表版本状态；第一期体验默认发布为“已发布”以便加载器读取",
    )
    parser.add_argument(
        "--skip-scales",
        action="store_true",
        help="跳过量表导入（仅刷新患者与关键词规则）",
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

    result: dict[str, object] = {}

    # 1) 演示医护账号
    result["staff"] = StaffSeeder().seed()

    # 2) 演示患者与住院记录
    result["patients"] = PatientSeeder().seed()

    # 3) 真实量表（导入并发布，供 AssessmentQuestionLoader 读取“已发布”版本）
    if not args.skip_scales:
        result["scales"] = AssessmentCatalogImporter().import_directory(
            args.scales_directory,
            publish_status=args.publish_status,
        )

    # 4) 关键词交互规则
    result["rules"] = InteractionRuleImporter().import_from_file()

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
