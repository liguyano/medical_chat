"""Schedule Agent 核心逻辑
作用：调度智能体，监控Dialog Agent对话进度，检测偏离，发布约束提示。
"""
import json
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.managers.assessment_loader import QuestionTask

logger = logging.getLogger(__name__)


class ScheduleAgentOutput(BaseModel):
    """Schedule Agent 输出 Schema
    作用：结构化输出调度结果
    """

    is_deviation: bool = Field(description="是否偏离量表问题")
    constraint_prompt: str = Field(default="", description="约束提示词（偏离时非空）")
    completed_questions: List[str] = Field(
        default_factory=list, description="已完成的问题编码列表"
    )
    remaining_questions: List[str] = Field(
        default_factory=list, description="待完成的问题编码列表"
    )
    missing_tool_calls: List[str] = Field(
        default_factory=list, description="遗漏的工具调用列表"
    )
    next_suggested_question: str = Field(default="", description="建议下一个提问")
    progress_percentage: float = Field(default=0.0, description="完成进度百分比")


class ScheduleAgent:
    """调度智能体
    作用：
    1. 监控Dialog Agent对话进度
    2. 基于LLM检测对话是否偏离量表问题
    3. 检查工具调用完整性
    4. 发布约束提示到Redis Stream
    """

    def __init__(
        self,
        session_id: str,
        task_list: List[QuestionTask],
        llm_client: Any,
        check_interval: int = 5,
    ):
        """初始化Schedule Agent
        Args:
            - session_id: 会话ID
            - task_list: 量表问题任务列表
            - llm_client: LLM客户端（OpenAI兼容接口）
            - check_interval: 检查间隔（每N轮对话检查一次）
        """
        self.session_id = session_id
        self.task_list = task_list
        self.llm_client = llm_client
        self.check_interval = check_interval
        self.turn_counter = 0  # 对话轮次计数器

        # 构建问题编码映射
        self.question_map = {q.question_code: q for q in task_list}

        logger.info(
            f"[Schedule Agent] 初始化: session={session_id}, 问题数={len(task_list)}, 检查间隔={check_interval}轮"
        )

    async def evaluate(
        self, dialog_history: List[Dict[str, str]]
    ) -> ScheduleAgentOutput:
        """评估对话进度并检测偏离
        作用：每5轮对话检查一次，判断是否偏离，检查工具调用
        Args:
            - dialog_history: 对话历史（LangChain格式）
                格式: [{"role": "assistant", "content": "..."}, {"role": "user", "content": "..."}]
        Return:
            - output: ScheduleAgentOutput结构化输出
        """
        self.turn_counter += 1

        # 1. 检查轮次，每N轮才执行检查
        if self.turn_counter % self.check_interval != 0:
            return self._skip_check()

        logger.info(f"[Schedule Agent] 第{self.turn_counter}轮检查: session={self.session_id}")

        # 2. 统计已完成和待完成的问题
        completed = await self._get_completed_questions(dialog_history)
        remaining = self._get_remaining_questions(completed)

        # 3. 检测对话偏离（调用 LLM）
        is_deviation = await self._check_deviation(dialog_history, remaining)

        # 4. 检查工具调用完整性
        missing_tools = await self._check_tool_calls(dialog_history)

        # 5. 生成约束提示
        constraint_prompt = self._build_constraint_prompt(
            is_deviation, missing_tools, remaining
        )

        # 6. 计算进度
        total = len(self.task_list)
        completed_count = len(completed)
        progress = (completed_count / total * 100) if total > 0 else 0.0

        output = ScheduleAgentOutput(
            is_deviation=is_deviation or bool(missing_tools),
            constraint_prompt=constraint_prompt,
            completed_questions=completed,
            remaining_questions=remaining,
            missing_tool_calls=missing_tools,
            next_suggested_question=remaining[0] if remaining else "",
            progress_percentage=round(progress, 2),
        )

        logger.info(
            f"[Schedule Agent] 检查结果: 偏离={output.is_deviation}, "
            f"进度={completed_count}/{total} ({output.progress_percentage}%)"
        )

        return output

    def _skip_check(self) -> ScheduleAgentOutput:
        """跳过本次检查，返回空结果
        作用：非检查轮次时，返回默认输出
        """
        return ScheduleAgentOutput(
            is_deviation=False,
            constraint_prompt="",
            completed_questions=[],
            remaining_questions=[q.question_code for q in self.task_list],
            missing_tool_calls=[],
        )

    async def _check_deviation(
        self, dialog_history: List[Dict[str, str]], remaining_questions: List[str]
    ) -> bool:
        """基于 LLM 判断对话是否偏离
        作用：调用LLM分析对话历史，判断是否偏离量表问题
        Args:
            - dialog_history: 对话历史
            - remaining_questions: 待完成的问题列表
        Return:
            - is_deviation: True表示偏离，False表示正常
        """
        try:
            # 构建提示词
            from .schedule_agent_prompts import (
                build_deviation_check_prompt,
                DEVIATION_CHECK_SYSTEM_PROMPT,
            )

            # 获取最近10轮对话
            recent_history = dialog_history[-20:] if len(dialog_history) > 20 else dialog_history

            # 获取待完成问题的详细信息
            remaining_tasks = [
                self.question_map[qc] for qc in remaining_questions if qc in self.question_map
            ]

            user_prompt = build_deviation_check_prompt(
                remaining_tasks=remaining_tasks,
                dialog_history=recent_history,
                turn_number=self.turn_counter,
            )

            # 调用 LLM
            response = await self.llm_client.chat.completions.create(
                model=self.llm_client.model,
                messages=[
                    {"role": "system", "content": DEVIATION_CHECK_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,  # 低温度，提高判断稳定性
                response_format={"type": "json_object"},  # 强制JSON输出
            )

            # 解析结果
            result_text = response.choices[0].message.content
            result = json.loads(result_text)

            is_deviation = result.get("is_deviation", False)
            reason = result.get("reason", "")

            if is_deviation:
                logger.warning(f"[Schedule Agent] 检测到偏离: {reason}")

            return is_deviation

        except Exception as e:
            logger.error(f"[Schedule Agent] 偏离检测失败: {e}")
            # 失败时默认返回False，避免误判
            return False

    async def _check_tool_calls(
        self, dialog_history: List[Dict[str, str]]
    ) -> List[str]:
        """检查是否遗漏工具调用
        作用：基于关键词规则检查对话中是否提到特征词但未调用相应工具
        Args:
            - dialog_history: 对话历史
        Return:
            - missing_tools: 遗漏的工具列表（例如 ["get_education_material(tobacco)"]）
        """
        missing_tools: List[str] = []

        # 关键词 -> 工具映射规则
        keyword_tool_map = {
            "抽烟": "get_education_material(category='tobacco')",
            "吸烟": "get_education_material(category='tobacco')",
            "喝酒": "get_education_material(category='alcohol')",
            "饮酒": "get_education_material(category='alcohol')",
            "手术": "trigger_consent_form(form_type='surgery')",
            "青霉素过敏": "remind_doctor_allergy",
            "药物过敏": "remind_doctor_allergy",
        }

        try:
            # 1. 收集对话中出现的关键词
            mentioned_keywords = set()
            for msg in dialog_history:
                if msg["role"] == "user":
                    content = msg["content"].lower()
                    for keyword in keyword_tool_map.keys():
                        if keyword in content:
                            mentioned_keywords.add(keyword)

            # 2. 检查是否调用了对应工具
            # 注意：这里简化处理，实际应该检查 tool_call 事件
            # TODO: 从 dialog_history 或 Redis Stream 读取 tool_call 事件
            called_tools = self._extract_tool_calls_from_history(dialog_history)

            # 3. 找出遗漏的工具
            for keyword in mentioned_keywords:
                tool_name = keyword_tool_map[keyword]
                # 简化判断：只检查工具名称前缀
                tool_prefix = tool_name.split("(")[0]
                if not any(tool_prefix in called for called in called_tools):
                    missing_tools.append(tool_name)

            if missing_tools:
                logger.warning(f"[Schedule Agent] 检测到遗漏工具: {missing_tools}")

        except Exception as e:
            logger.error(f"[Schedule Agent] 工具调用检查失败: {e}")

        return missing_tools

    def _extract_tool_calls_from_history(
        self, dialog_history: List[Dict[str, str]]
    ) -> List[str]:
        """从对话历史中提取已调用的工具
        作用：解析对话中的工具调用记录
        Args:
            - dialog_history: 对话历史
        Return:
            - called_tools: 已调用的工具名称列表
        """
        # TODO: 实际应该从 Redis Stream 的 tool_call 事件中读取
        # 这里简化处理，从对话内容中查找工具调用标记
        called_tools = []
        for msg in dialog_history:
            if msg["role"] == "assistant":
                content = msg["content"]
                # 假设工具调用会在消息中体现（实际应该是独立事件）
                if "宣教" in content or "教育材料" in content:
                    called_tools.append("get_education_material")
                if "知情同意" in content:
                    called_tools.append("trigger_consent_form")
        return called_tools

    async def _get_completed_questions(
        self, dialog_history: List[Dict[str, str]]
    ) -> List[str]:
        """从对话历史中识别已完成的问题
        作用：分析对话，判断哪些问题已经得到回答
        Args:
            - dialog_history: 对话历史
        Return:
            - completed: 已完成的问题编码列表
        """
        # TODO: 这里应该调用 LLM 或使用 Field Extraction Agent 的结果
        # 暂时简化：假设每个问题被提及且患者回答了，就算完成
        completed = []

        try:
            # 简化实现：检查问题文本是否出现在对话中
            for task in self.task_list:
                question_text = task.patient_text
                for msg in dialog_history:
                    if msg["role"] == "assistant" and question_text in msg["content"]:
                        # AI提问了
                        # 检查下一条是否有患者回答
                        idx = dialog_history.index(msg)
                        if idx + 1 < len(dialog_history):
                            next_msg = dialog_history[idx + 1]
                            if next_msg["role"] == "user" and len(next_msg["content"]) > 3:
                                completed.append(task.question_code)
                                task.completed = True
                                break

        except Exception as e:
            logger.error(f"[Schedule Agent] 统计已完成问题失败: {e}")

        return completed

    def _get_remaining_questions(self, completed: List[str]) -> List[str]:
        """获取待完成的问题列表
        Args:
            - completed: 已完成的问题编码列表
        Return:
            - remaining: 待完成的问题编码列表
        """
        return [
            q.question_code
            for q in self.task_list
            if q.question_code not in completed
        ]

    def _build_constraint_prompt(
        self,
        is_deviation: bool,
        missing_tools: List[str],
        remaining_questions: List[str],
    ) -> str:
        """生成约束提示词
        作用：当偏离或遗漏工具时，生成具体的约束提示
        Args:
            - is_deviation: 是否偏离
            - missing_tools: 遗漏的工具列表
            - remaining_questions: 待完成问题列表
        Return:
            - constraint_prompt: 约束提示词
        """
        if not is_deviation and not missing_tools:
            return ""

        prompts = []

        if is_deviation and remaining_questions:
            next_question_code = remaining_questions[0]
            if next_question_code in self.question_map:
                next_task = self.question_map[next_question_code]
                prompts.append(
                    f"你偏离了量表问题列表，请回到问题：{next_task.patient_text}"
                )

        if missing_tools:
            tool_prompts = []
            for tool in missing_tools:
                if "tobacco" in tool:
                    tool_prompts.append("你必须对患者进行抽烟相关的健康宣教")
                elif "alcohol" in tool:
                    tool_prompts.append("你必须对患者进行饮酒相关的健康宣教")
                elif "surgery" in tool:
                    tool_prompts.append("你必须让患者阅读手术知情同意书")
                elif "allergy" in tool:
                    tool_prompts.append("你必须提醒患者下次就医时告知医生药物过敏史")
            prompts.extend(tool_prompts)

        return "\n".join(prompts)
