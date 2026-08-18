"""关键词拦截中间件
作用：从 interaction_rule 表加载规则，匹配患者输入，命中则追加约束。
"""
import logging
from typing import Any

from .base import DialogMiddleware

logger = logging.getLogger(__name__)


class KeywordInterceptMiddleware(DialogMiddleware):
    """关键词拦截中间件
    作用：检测患者输入中的关键词（抽烟/饮酒/过敏等），触发约束提示。
    """

    def __init__(self, session_factory=None):
        """初始化关键词拦截中间件
        Args:
            - session_factory: 数据库会话工厂（用于查询 interaction_rule 表）
        """
        self.session_factory = session_factory
        # 内置最小关键词库（interaction_rule 表未就绪时的降级方案）
        self.builtin_keywords = {
            "抽烟": (
                "你必须追问吸烟频率与数量，调用 get_education_material(category='tobacco')，"
                "并触发 trigger_consent_form(form_type='tobacco')"
            ),
            "吸烟": (
                "你必须追问吸烟频率与数量，调用 get_education_material(category='tobacco')，"
                "并触发 trigger_consent_form(form_type='tobacco')"
            ),
            "喝酒": "你必须对患者进行饮酒相关的健康宣教，调用 get_education_material(category='alcohol')",
            "饮酒": "你必须对患者进行饮酒相关的健康宣教，调用 get_education_material(category='alcohol')",
            "手术": "你必须让患者阅读手术知情同意书，调用 trigger_consent_form(form_type='surgery')",
            "青霉素过敏": (
                "你必须追问过敏反应，调用 get_education_material(category='allergy', level=3)，"
                "并提醒患者下次就医时主动告知医生和护士"
            ),
            "药物过敏": (
                "你必须追问具体过敏药物名称和反应，"
                "调用 get_education_material(category='allergy', level=3)"
            ),
        }
        logger.info("[KeywordInterceptMiddleware] 初始化完成")

    async def before_agent(self, context: dict[str, Any]) -> None:
        """执行前钩子：检测关键词并注入约束
        Args:
            - context: 上下文字典，包含 patient_input、constraints 等
        """
        patient_input = context.get("patient_input", "")
        if not patient_input:
            return

        # TODO: 从 interaction_rule 表加载规则（批次B）
        # 当前使用内置关键词库
        negative_phrases = {
            "抽烟": ("不抽烟", "从不抽烟", "已经戒烟"),
            "吸烟": ("不吸烟", "从不吸烟", "已经戒烟"),
            "喝酒": ("不喝酒", "从不喝酒", "已经戒酒"),
            "饮酒": ("不饮酒", "从不饮酒", "已经戒酒"),
            "手术": ("不做手术", "无需手术"),
        }
        matched_constraints: list[str] = []
        for keyword, constraint in self.builtin_keywords.items():
            negatives = negative_phrases.get(keyword, ())
            if keyword in patient_input and not any(
                phrase in patient_input for phrase in negatives
            ):
                matched_constraints.append(constraint)
                logger.info(
                    f"[KeywordInterceptMiddleware] 命中关键词: {keyword} "
                    f"-> 约束: {constraint[:50]}..."
                )

        if matched_constraints:
            # 追加到 context.constraints 列表
            if "constraints" not in context:
                context["constraints"] = []
            existing = context["constraints"]
            existing.extend(
                constraint
                for constraint in matched_constraints
                if constraint not in existing
            )

    async def after_agent(self, context: dict[str, Any], output: Any) -> None:
        """执行后钩子：关键词拦截无需 after 处理
        Args:
            - context: 上下文字典
            - output: 智能体输出
        """
