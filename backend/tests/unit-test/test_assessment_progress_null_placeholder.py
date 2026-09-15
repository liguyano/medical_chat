"""结构化评估进度中的 null 占位答案回归测试。"""

from sqlalchemy import create_engine, select

from app.models.assessment_execution import AssessmentAnswer
from app.services.assessment_progress_service import valid_assessment_answer_condition


def test_literal_null_text_is_unanswered_but_real_values_remain_valid():
    """文本 null 可保留在库中，但不能推进评估完成进度。"""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TABLE assessment_answer (
                id INTEGER PRIMARY KEY,
                answer_text TEXT,
                answer_number NUMERIC,
                answer_boolean BOOLEAN,
                answer_date DATE,
                answer_time TIME,
                answer_datetime DATETIME,
                extraction_confidence NUMERIC
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE assessment_answer_option (
                id INTEGER PRIMARY KEY,
                assessment_answer_id INTEGER,
                selected_flag BOOLEAN,
                deleted INTEGER
            )
            """
        )
        conn.exec_driver_sql(
            """
            INSERT INTO assessment_answer (
                id, answer_text, answer_number, answer_boolean,
                answer_date, answer_time, answer_datetime, extraction_confidence
            ) VALUES
                (1, 'null', NULL, NULL, NULL, NULL, NULL, 0.95),
                (2, ' NULL ', NULL, NULL, NULL, NULL, NULL, 0.95),
                (3, '正常进食', NULL, NULL, NULL, NULL, NULL, 0.95),
                (4, NULL, NULL, NULL, NULL, NULL, NULL, 0.95),
                (5, NULL, 0, NULL, NULL, NULL, NULL, 0.95)
            """
        )

        valid_ids = conn.execute(
            select(AssessmentAnswer.id)
            .where(valid_assessment_answer_condition())
            .order_by(AssessmentAnswer.id)
        ).scalars().all()

    assert valid_ids == [3, 5]
