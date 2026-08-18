"""Schedule Agent 核心逻辑
作用：监控量表对话进度、检测语义偏离并检查关键工具调用。
"""

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError

from .models import (
    QuestionTask,
    ScheduleAgentOutput,
    ScheduleAnalysis,
    SchedulePlanDraft,
    ScheduleTaskTodo,
    ToolCallRecord,
)
from .prompts import (
    DEVIATION_CHECK_SYSTEM_PROMPT,
    TASK_TODO_SYSTEM_PROMPT,
    build_deviation_check_prompt,
    build_task_todo_prompt,
)

logger = logging.getLogger(__name__)


class ScheduleAgent:
    """量表评估调度智能体。"""

    def __init__(
        self,
        session_id: str,
        task_list: list[QuestionTask],
        model: BaseChatModel,
        *,
        check_interval: int = 5,
    ) -> None:
        """初始化调度智能体
        Args:
            - session_id: 交互会话编号
            - task_list: 量表问题任务列表
            - model: LangChain BaseChatModel（temperature/max_tokens 等在模型构造时注入）
            - check_interval: 每隔多少轮执行一次检查
        """
        if check_interval <= 0:
            raise ValueError("check_interval 必须大于 0")

        self.session_id = session_id
        self.task_list = task_list
        self.model = model
        self.check_interval = check_interval
        self.turn_counter = 0
        self.completed_question_codes: set[str] = {
            task.question_code for task in task_list if task.completed
        }
        self.question_map = {task.question_code: task for task in task_list}

    async def prepare_task_todo(
        self,
        patient_info: dict[str, Any],
    ) -> ScheduleTaskTodo:
        """生成会话级 Task-todo
        作用：由 Schedule Agent 规划问题顺序；模型失败时使用确定性顺序，
        确保首问预热不会因规划模型异常而永久阻塞。
        """
        grouped: dict[str, list[QuestionTask]] = {}
        for task in self.task_list:
            if not task.required:
                continue
            grouped.setdefault(task.question_code, []).append(task)

        draft = await self._plan_task_todo(patient_info)
        ordered_codes: list[str] = []
        for code in draft.ordered_question_codes:
            if code in grouped and code not in ordered_codes:
                ordered_codes.append(code)
        for task in self.task_list:
            if (
                task.required
                and task.question_code in grouped
                and task.question_code not in ordered_codes
            ):
                ordered_codes.append(task.question_code)

        planned_tasks: list[QuestionTask] = []
        for code in ordered_codes:
            sources = grouped[code]
            primary = sources[0]
            planned_tasks.append(
                primary.model_copy(
                    update={
                        "source_question_ids": [item.question_id for item in sources],
                        "dialogue_goal": primary.question_name,
                    }
                )
            )
        return ScheduleTaskTodo(
            session_id=self.session_id,
            tasks=planned_tasks,
            opening_guidance=draft.opening_guidance,
            planning_reason=draft.planning_reason,
        )

    async def _plan_task_todo(
        self,
        patient_info: dict[str, Any],
    ) -> SchedulePlanDraft:
        """调用模型生成 Task-todo 草稿。"""
        messages = [
            SystemMessage(content=TASK_TODO_SYSTEM_PROMPT),
            HumanMessage(
                content=build_task_todo_prompt(
                    patient_info=patient_info,
                    questions=self.task_list,
                )
            ),
        ]
        try:
            structured = self.model.with_structured_output(SchedulePlanDraft)
            result = await structured.ainvoke(messages)
            return (
                result
                if isinstance(result, SchedulePlanDraft)
                else SchedulePlanDraft.model_validate(result)
            )
        except Exception:
            logger.exception("[Schedule Agent] Task-todo 规划失败，使用确定性顺序")
            return SchedulePlanDraft(
                opening_guidance=(
                    "按 CICARE 完成身份核实、自我介绍和流程说明后，"
                    "自然询问第一个待评估问题。"
                ),
                planning_reason="模型规划失败，使用量表审核顺序",
            )

    async def evaluate(
        self,
        dialog_history: list[dict[str, str]],
        *,
        tool_calls: list[ToolCallRecord | dict[str, Any]] | None = None,
        force: bool = False,
    ) -> ScheduleAgentOutput:
        """评估一次对话轮次
        作用：按检查间隔调用 LLM，并合并进度与工具完整性结果。
        """
        self.turn_counter += 1
        if not force and self.turn_counter % self.check_interval != 0:
            return self._build_output(checked=False)

        remaining_before_check = self._remaining_codes()
        analysis = await self._analyze_dialog(dialog_history, remaining_before_check)
        self._merge_completed_questions(analysis.completed_questions)

        normalized_calls: list[ToolCallRecord] = []
        for call in tool_calls or []:
            try:
                normalized_calls.append(
                    call
                    if isinstance(call, ToolCallRecord)
                    else ToolCallRecord.model_validate(call)
                )
            except ValidationError:
                logger.warning("[Schedule Agent] 忽略无效工具调用记录: %r", call)
        missing_tools = self._check_tool_calls(dialog_history, normalized_calls)
        remaining = self._remaining_codes()
        constraint_prompt = self._build_constraint_prompt(
            analysis=analysis,
            missing_tools=missing_tools,
            remaining_questions=remaining,
        )
        return self._build_output(
            checked=True,
            is_deviation=analysis.is_deviation or bool(missing_tools),
            constraint_prompt=constraint_prompt,
            missing_tools=missing_tools,
        )

    def restore_state(self, state: dict[str, Any]) -> None:
        """恢复 Redis 中的轻量运行状态。"""
        self.turn_counter = max(int(state.get("turn_counter", 0)), 0)
        completed = state.get("completed_questions", [])
        if isinstance(completed, list):
            self._merge_completed_questions(completed)

    def dump_state(self) -> dict[str, Any]:
        """导出可持久化的轻量运行状态。"""
        return {
            "turn_counter": self.turn_counter,
            "completed_questions": self._completed_codes(),
        }

    async def _analyze_dialog(
        self,
        dialog_history: list[dict[str, str]],
        remaining_questions: list[str],
    ) -> ScheduleAnalysis:
        """调用 OpenAI 兼容接口执行语义判断。"""
        remaining_tasks = [
            self.question_map[code]
            for code in remaining_questions
            if code in self.question_map
        ]
        prompt = build_deviation_check_prompt(
            remaining_tasks=remaining_tasks,
            dialog_history=dialog_history[-20:],
            turn_number=self.turn_counter,
        )
        messages = [
            SystemMessage(content=DEVIATION_CHECK_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]

        model_name = getattr(self.model, "model_name", None) or getattr(
            self.model,
            "model",
            "unknown",
        )
        logger.info(
            "[Schedule Agent] 调用真实模型: session=%s, model=%s, remaining=%s",
            self.session_id,
            model_name,
            len(remaining_questions),
        )
        try:
            structured = self.model.with_structured_output(ScheduleAnalysis)
            result = await structured.ainvoke(messages)
            if isinstance(result, ScheduleAnalysis):
                logger.info(
                    "[Schedule Agent] 真实模型结构化响应成功: session=%s, deviation=%s",
                    self.session_id,
                    result.is_deviation,
                )
                return result
            # 少数供应商可能返回 dict，做一次兜底校验
            normalized = ScheduleAnalysis.model_validate(result)
            logger.info(
                "[Schedule Agent] 真实模型结构化响应成功: session=%s, deviation=%s",
                self.session_id,
                normalized.is_deviation,
            )
            return normalized
        except (AttributeError, TypeError, ValueError, ValidationError):
            logger.exception("[Schedule Agent] LLM 结构化响应解析失败")
        except Exception:
            logger.exception("[Schedule Agent] LLM 调用失败")
        return ScheduleAnalysis()

    def _merge_completed_questions(self, question_codes: list[str]) -> None:
        """只接纳当前量表中存在的问题编码。"""
        valid_codes = set(question_codes) & self.question_map.keys()
        self.completed_question_codes.update(valid_codes)
        for code in valid_codes:
            self.question_map[code].completed = True

    def _check_tool_calls(
        self,
        dialog_history: list[dict[str, str]],
        tool_calls: list[ToolCallRecord],
    ) -> list[str]:
        """检查最近对话命中的宣教/同意工具是否已正确调用。"""
        recent_user_text = "\n".join(
            message.get("content", "")
            for message in dialog_history[-10:]
            if message.get("role") == "user"
        )
        requirements = [
            (
                ("抽烟", "吸烟"),
                ("不抽烟", "不吸烟", "已经戒烟", "戒烟了"),
                "get_education_material",
                {"category": "tobacco"},
                "get_education_material(category='tobacco')",
            ),
            (
                ("抽烟", "吸烟"),
                ("不抽烟", "不吸烟", "已经戒烟", "戒烟了"),
                "trigger_consent_form",
                {"form_type": "tobacco"},
                "trigger_consent_form(form_type='tobacco')",
            ),
            (
                ("喝酒", "饮酒"),
                ("不喝酒", "不饮酒", "已经戒酒", "戒酒了"),
                "get_education_material",
                {"category": "alcohol"},
                "get_education_material(category='alcohol')",
            ),
            (
                ("手术",),
                ("不做手术", "无需手术"),
                "trigger_consent_form",
                {"form_type": "surgery"},
                "trigger_consent_form(form_type='surgery')",
            ),
            (
                ("青霉素过敏", "药物过敏"),
                ("无药物过敏", "没有药物过敏", "不过敏"),
                "get_education_material",
                {"category": "allergy"},
                "get_education_material(category='allergy')",
            ),
        ]

        missing: list[str] = []
        for keywords, negative_phrases, tool_name, expected_arguments, label in requirements:
            has_positive_feature = any(
                keyword in recent_user_text for keyword in keywords
            ) and not any(
                negative in recent_user_text for negative in negative_phrases
            )
            if not has_positive_feature:
                continue
            matched = any(
                call.name == tool_name
                and all(call.arguments.get(key) == value for key, value in expected_arguments.items())
                for call in tool_calls
            )
            if not matched:
                missing.append(label)
        return missing

    def _build_constraint_prompt(
        self,
        *,
        analysis: ScheduleAnalysis,
        missing_tools: list[str],
        remaining_questions: list[str],
    ) -> str:
        """组合偏离引导和工具补偿约束。"""
        prompts: list[str] = []
        if analysis.is_deviation:
            if analysis.suggested_action:
                prompts.append(analysis.suggested_action)
            elif remaining_questions:
                prompts.append(
                    f"请结束无关话题，并自然引导患者回答："
                    f"{self.question_map[remaining_questions[0]].patient_text}"
                )

        for tool in missing_tools:
            if "tobacco" in tool:
                if "consent" in tool:
                    prompts.append("必须触发戒烟知情宣教书。")
                else:
                    prompts.append("必须调用戒烟宣教工具，并完成吸烟频率与吸烟量追问。")
            elif "alcohol" in tool:
                prompts.append("必须调用饮酒宣教工具，并完成饮酒频率与饮酒量追问。")
            elif "surgery" in tool:
                prompts.append("必须调用手术知情同意书工具，引导患者阅读并确认。")
            elif "allergy" in tool:
                prompts.append("必须完成药物过敏安全宣教并提醒患者以后就医主动告知医护人员。")
        return "\n".join(dict.fromkeys(prompts))

    def _build_output(
        self,
        *,
        checked: bool,
        is_deviation: bool = False,
        constraint_prompt: str = "",
        missing_tools: list[str] | None = None,
    ) -> ScheduleAgentOutput:
        """根据当前累积状态构建输出。"""
        completed = self._completed_codes()
        remaining = self._remaining_codes()
        total = len(self.task_list)
        progress = round(len(completed) / total * 100, 2) if total else 100.0
        next_question = (
            self.question_map[remaining[0]].patient_text if remaining else ""
        )
        return ScheduleAgentOutput(
            checked=checked,
            is_deviation=is_deviation,
            constraint_prompt=constraint_prompt,
            completed_questions=completed,
            remaining_questions=remaining,
            missing_tool_calls=missing_tools or [],
            next_suggested_question=next_question,
            progress_percentage=progress,
        )

    def _completed_codes(self) -> list[str]:
        """按量表原始顺序返回已完成问题。"""
        return [
            task.question_code
            for task in self.task_list
            if task.question_code in self.completed_question_codes
        ]

    def _remaining_codes(self) -> list[str]:
        """按量表原始顺序返回待完成问题。"""
        return [
            task.question_code
            for task in self.task_list
            if task.question_code not in self.completed_question_codes
        ]
