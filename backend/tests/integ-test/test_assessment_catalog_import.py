"""真实结构化量表 PostgreSQL 导入与加载集成测试。"""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.managers.assessment_catalog_importer import AssessmentCatalogImporter
from app.managers.assessment_loader import AssessmentQuestionLoader
from app.models import (
    AssessmentActionDefinition,
    AssessmentOption,
    AssessmentQuestion,
    AssessmentScale,
    AssessmentScaleVersion,
)

CATALOG_DIR = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "structured"
    / "assessment-scales"
)
@pytest.fixture
def isolated_catalog(tmp_path):
    """复制真实量表并为主档编码追加随机后缀，避免依赖开发库为空。"""
    suffix = uuid4().hex[:8]
    index = json.loads((CATALOG_DIR / "index.json").read_text(encoding="utf-8"))
    scale_codes: list[str] = []
    for form in index["forms"]:
        path = CATALOG_DIR / form["structured_file"]
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["id"] = f"{payload['id']}_{suffix}"
        form["id"] = payload["id"]
        scale_codes.append(payload["id"])
        (tmp_path / form["structured_file"]).write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
    (tmp_path / "index.json").write_text(
        json.dumps(index, ensure_ascii=False),
        encoding="utf-8",
    )
    return tmp_path, scale_codes


def test_import_all_real_scales_is_idempotent(
    postgres_session_factory,
    isolated_catalog,
):
    """十六份真实量表应完整导入，重复执行不产生重复版本。"""
    catalog_dir, _ = isolated_catalog
    importer = AssessmentCatalogImporter(postgres_session_factory)
    first = importer.import_directory(catalog_dir, publish_status="已发布")
    second = importer.import_directory(catalog_dir, publish_status="已发布")

    assert first["scales"] == 16
    assert first["versions"] == 16
    assert first["questions"] >= 140
    assert first["options"] > 280
    assert first["actions"] == 53
    assert second["versions"] == 0
    assert second["skipped_versions"] == 16

    with postgres_session_factory() as db:
        imported_scale_ids = db.scalars(
            select(AssessmentScale.id).where(
                AssessmentScale.scale_code.like(f"%{isolated_catalog[1][0][-8:]}")
            )
        ).all()
        assert len(imported_scale_ids) == 16
        version_ids = db.scalars(
            select(AssessmentScaleVersion.id).where(
                AssessmentScaleVersion.scale_id.in_(imported_scale_ids)
            )
        ).all()
        assert len(version_ids) == 16
        assert (
            db.scalar(
                select(func.count(AssessmentQuestion.id)).where(
                    AssessmentQuestion.scale_version_id.in_(version_ids)
                )
            )
            == first["questions"]
        )
        assert (
            db.scalar(
                select(func.count(AssessmentOption.id))
                .join(
                    AssessmentQuestion,
                    AssessmentQuestion.id == AssessmentOption.question_id,
                )
                .where(AssessmentQuestion.scale_version_id.in_(version_ids))
            )
            == first["options"]
        )
        assert (
            db.scalar(
                select(func.count(AssessmentActionDefinition.id)).where(
                    AssessmentActionDefinition.scale_version_id.in_(version_ids)
                )
            )
            == first["actions"]
        )


@pytest.mark.asyncio
async def test_loader_returns_published_questions_options_and_order(
    postgres_session_factory,
    isolated_catalog,
):
    """加载器应返回全部已发布问题、选项和稳定顺序，并排除派生题。"""
    catalog_dir, scale_codes = isolated_catalog
    AssessmentCatalogImporter(postgres_session_factory).import_directory(
        catalog_dir,
        publish_status="已发布",
    )
    loader = AssessmentQuestionLoader(postgres_session_factory)
    tasks = await loader.load_questions_by_scale_codes(scale_codes)

    with postgres_session_factory() as db:
        version_ids = db.scalars(
            select(AssessmentScaleVersion.id)
            .join(AssessmentScale, AssessmentScale.id == AssessmentScaleVersion.scale_id)
            .where(AssessmentScale.scale_code.in_(scale_codes))
        ).all()
        total_questions = db.scalar(
            select(func.count(AssessmentQuestion.id)).where(
                AssessmentQuestion.scale_version_id.in_(version_ids)
            )
        )
        derived_questions = db.scalar(
            select(func.count(AssessmentQuestion.id)).where(
                AssessmentQuestion.scale_version_id.in_(version_ids),
                AssessmentQuestion.derived.is_(True),
            )
        )
    assert len(tasks) == total_questions - derived_questions
    assert {task.scale_code for task in tasks} == set(scale_codes)
    loaded_codes = {task.question_code for task in tasks}
    assert "bmi" not in loaded_codes
    assert "weight_loss_percent" not in loaded_codes
    assert "age_score" not in loaded_codes
    assert "adl_score" not in loaded_codes
    assert "fall_score" not in loaded_codes
    adl_code = next(code for code in scale_codes if code.startswith("adl_"))
    adl_tasks = [task for task in tasks if task.scale_code == adl_code]
    assert [task.question_code for task in adl_tasks[:2]] == ["feeding", "bathing"]
    assert [option.clinical_score for option in adl_tasks[0].options] == [
        0.0,
        5.0,
        10.0,
    ]
    iadl_code = next(code for code in scale_codes if code.startswith("iadl_lawton_brody_"))
    iadl_tasks = [task for task in tasks if task.scale_code == iadl_code]
    assert iadl_tasks[0].patient_text == "最近1个月，您上街购物通常能做到什么程度？"


@pytest.mark.asyncio
async def test_pending_review_catalog_is_not_executable(
    postgres_session_factory,
    isolated_catalog,
):
    """审核中量表不可执行，同内容审核发布后应原地晋升而非复制版本。"""
    catalog_dir, scale_codes = isolated_catalog
    adl_code = next(code for code in scale_codes if code.startswith("adl_"))
    importer = AssessmentCatalogImporter(postgres_session_factory)
    importer.import_directory(catalog_dir)
    loader = AssessmentQuestionLoader(postgres_session_factory)
    assert await loader.load_questions_by_scale_codes([adl_code]) == []

    promoted = importer.import_directory(catalog_dir, publish_status="已发布")
    assert promoted["promoted_versions"] == 16
    assert promoted["versions"] == 0
    assert await loader.load_questions_by_scale_codes([adl_code])
