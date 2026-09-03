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
    return (
        "【本轮选题约束，优先于历史 Task-todo 和旧 Schedule 建议】\n"
        "每轮回复前必须先调用 report_question_choice，工具成功后才向患者说话。"
        "本轮最多选择一个候选问题，selected_question_id 与 active_question_id 均填该题 ID。"
        "候选只是可选方向，不是本轮必须完成的清单，不能一次询问三个问题。"
        "如果上一个问题未问清、患者话题未聊完或患者正在提问，可以完全不问新题："
        "selected_question_id=null；仅在确实澄清当前题时保留 active_question_id，"
        "普通回应或聊天时 active_question_id=null。不要因返回 null 而沉默或宣布评估完成。"
        "候选为空也可自然回应，不要自行从历史问题中选新题。"
        "已记录的事实不得重复询问。患者说问过了时先根据历史回答回应，"
        "确实缺信息才说明需要补充什么，禁止原样轮流重复。"
        "准备选择已问待确认的候选时先回看历史：若患者已经明确回答，不要重新询问，"
        "本轮可返回 null，等待后台抽取；若答案不清楚，才有针对性澄清。"
        "工具参数、题目编号、冷却和抽取流程均不向患者朗读。\n"
        + json.dumps(payload, ensure_ascii=False, default=str)
    )


@dataclass
class QuestionTurnSelection:
    """一次患者交互的选择；没有合法报告时不放行患者可见增量。"""

    context: dict[str, Any]
    decision: dict[str, Any] | None = None
    confirmed_decision: dict[str, Any] | None = None
    failed_reports: int = 0
    cancelled: bool = False

    @property
    def allow_output(self) -> bool:
        return self.decision is not None and not self.cancelled

    def report(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from app.services.dialog_question_service import validate_decision

        if self.cancelled:
            return {"success": False, "message": "本轮已取消，请等待患者下一次发言"}
        try:
            decision = validate_decision(self.context, arguments)
        except (ValueError, TypeError, KeyError) as exc:
            self.failed_reports += 1
            self.decision = None
            return {"success": False, "message": str(exc), "retry_selection": True}
        if self.confirmed_decision is not None and decision != self.confirmed_decision:
            self.failed_reports += 1
            self.decision = None
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
