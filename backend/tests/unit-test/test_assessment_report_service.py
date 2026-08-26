"""评估报告结构化输出单元测试。"""

from app.services.assessment_report_service import _parse_model_output


def test_parse_assessment_report_json_code_fence():
    """报告模型返回代码围栏时应正常解析。"""
    report = _parse_model_output(
        '```json\n'
        '{"overall_summary":"总体稳定","key_findings":["完成评估"],'
        '"risk_overview":["跌倒风险"],"nursing_focus":["陪同下床"],'
        '"follow_up_suggestions":["24小时复评"]}\n```'
    )
    assert report.overall_summary == "总体稳定"
    assert report.nursing_focus == ["陪同下床"]
