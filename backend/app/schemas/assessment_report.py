"""评估报告 Schema
作用：定义 LLM 结构化输出、报告详情和版本列表响应。
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AiAssessmentReportOutput(BaseModel):
    """LLM 生成的综合报告内容，不承载量表原始分数。"""

    overall_summary: str = Field(..., min_length=1, max_length=4000)
    key_findings: list[str] = Field(default_factory=list, max_length=30)
    risk_overview: list[str] = Field(default_factory=list, max_length=30)
    nursing_focus: list[str] = Field(default_factory=list, max_length=30)
    follow_up_suggestions: list[str] = Field(default_factory=list, max_length=30)


class AssessmentReportVersionDto(BaseModel):
    """报告历史版本摘要。"""

    id: int
    version_no: int
    report_status: str
    generated_by: str
    generated_at: str
    confirmed_by: int | None = None
    confirmed_at: str | None = None


class AssessmentReportDto(AssessmentReportVersionDto):
    """评估报告完整响应。"""

    report_no: str
    task_id: int
    source_submission_ids: list[int]
    source_snapshot: dict[str, Any]
    report_content: AiAssessmentReportOutput
    versions: list[AssessmentReportVersionDto] = Field(default_factory=list)


class AssessmentReportGenerateRequest(BaseModel):
    """生成新报告版本请求。"""

    model_config = ConfigDict(extra="forbid")
    force: bool = False
