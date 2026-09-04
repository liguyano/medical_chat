"""文字与语音共用的单轮选题提示及输出门禁。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


def build_question_turn_prompt(context: dict[str, Any]) -> str:
    """只传递候选、当前题与已记录摘要，不暴露其他待问题让模型绕过冷却。"""
    candidate_ids = set(context.get("candidate_question_ids") or [])
    active_id = context.get("active_question_id")
    questions = context.get("questions") or []
    payload = {
        "candidate_questions": [q for q in questions if q["question_id"] in candidate_ids],
        "active_question": next((q for q in questions if q["question_id"] == active_id), None),
        "recorded_answers": context.get("recorded_answers") or [],
        "recorded_count": context.get("current", 0),
        "required_count": context.get("total", 0),
    }
    if candidate_ids and active_id is None:
        liveness_rule = (
            "当前候选非空且没有正在澄清的当前题，不能返回 null/null。"
            "即使患者刚才在聊其他事情，也应先简短回应，再从 candidate_questions 中选择一题继续完成评估。"
            "如果候选题状态为 asked，说明此前虽然问过，但后台仍没有形成有效结构化答案；"
            "不要继续泛聊或无限等待抽取，应换一种自然、针对性的方式确认该题。"
        )
    elif candidate_ids:
        liveness_rule = (
            "当前仍有候选题，同时存在正在处理的 active_question。"
            "确实需要澄清当前题时可以 selected_question_id=null 并保留 active_question_id；"
            "当前题已经说明清楚并准备推进时，应从 candidate_questions 选择一题继续完成评估。"
        )
    else:
        liveness_rule = (
            "当前没有可用候选题，可能仍处于冷却或等待后台状态更新；"
            "此时允许 null/null 自然回应，但不要自行从历史问题中伪造新题，也不要宣布评估完成。"
        )
    return (
        "【本轮选题约束，优先于历史 Task-todo 和旧 Schedule 建议】\n"
        "先根据 candidate_questions 与 active_question 决定本轮实际要回应或询问的内容；"
        "在本轮完成前调用 report_question_choice 报告实际选择。"
        "该工具仅用于记录题目关联，不是患者可见回复的前置门禁；"
        "可以先自然回应患者，再报告本轮真正选择的题目，但报告必须与实际回复一致。"
        "本轮最多选择一个候选问题，selected_question_id 与 active_question_id 均填该题 ID。"
        "新问题只能从 candidate_questions 中选择；候选为空时不得绕过冷却从历史中找题。"
        "患者提出额外问题时先简短回答，但不能因此长期停留在泛聊而不推进仍未完成的必填评估。"
        f"{liveness_rule}"
        "已记录的事实不得重复询问。患者说问过了时先根据历史回答回应，"
        "如果该题仍作为候选出现，说明有效结构化答案尚未确认，应针对缺失信息重新确认，"
        "而不是原样轮流重复问题或一直等待。"
        "工具参数、题目编号、冷却和抽取流程均不向患者朗读。\n"
        + json.dumps(payload, ensure_ascii=False, default=str)
    )


@dataclass
class QuestionTurnSelection:
    """一次患者交互的选题记录；报告用于关联题目，不作为患者输出门禁。"""

    context: dict[str, Any]
    decision: dict[str, Any] | None = None
    confirmed_decision: dict[str, Any] | None = None
    failed_reports: int = 0
    cancelled: bool = False

    @property
    def allow_output(self) -> bool:
        """患者输出只受取消状态约束，不再依赖选题工具是否已报告。"""
        return not self.cancelled

    def report(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from app.services.dialog_question_service import validate_decision

        if self.cancelled:
            return {"success": False, "message": "本轮已取消，请等待患者下一次发言"}
        try:
            decision = validate_decision(self.context, arguments)
            if (
                self.context.get("candidate_question_ids")
                and self.context.get("active_question_id") is None
                and decision["selected_question_id"] is None
                and decision["active_question_id"] is None
            ):
                raise ValueError(
                    "当前仍有可问候选，不能继续普通聊天；请从候选中选择一题继续完成评估"
                )
        except (ValueError, TypeError, KeyError) as exc:
            self.failed_reports += 1
            return {"success": False, "message": str(exc), "retry_selection": True}
        if self.confirmed_decision is not None and decision != self.confirmed_decision:
            self.failed_reports += 1
            return {
                "success": False,
                "message": "本轮已经确认选题，不可再次更换；请按已确认选择回复",
            }
        self.decision = decision
        self.confirmed_decision = decision
        return {
            "success": True,
            **decision,
            "message": "选择已确认，请自然回应患者；仅实际选新题才推进提问",
        }

    def require_decision(self) -> dict[str, Any]:
        if not self.allow_output:
            raise RuntimeError("模型未报告有效选题，本轮回复未放行")
        assert self.decision is not None
        return self.decision
