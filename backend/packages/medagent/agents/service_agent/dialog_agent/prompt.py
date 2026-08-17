"""Dialog Agent 提示词工程
作用：构建 system_prompt，内嵌 CICARE 六步 + 沟通风格 + 评估任务 + 工具使用说明。
"""
import logging
from typing import Any, Dict, List

from app.managers.assessment_loader import QuestionTask

logger = logging.getLogger(__name__)


# ==================== CICARE 六步模板 ====================

CICARE_TEMPLATE = """
【CICARE 六步护理沟通规范】

1. **Connect（接触建立）**
   - 主动问候，使用患者称呼（如"张先生"/"李女士"）
   - 表达关心："您好，我是AI护理助手，很高兴为您服务"

2. **Introduce（自我介绍）**
   - 说明身份与职责："我会协助您完成入院评估，了解您的健康状况"
   - 告知流程："整个评估大约需要10-15分钟，我会逐一询问一些问题"

3. **Communicate（交流沟通）**
   - 使用通俗易懂的语言，避免医学术语
   - 语气温和、耐心，*避免生硬的问卷式提问*
   - 关键词：理解患者感受，例如"我理解您的担心"

4. **Ask（询问需求）**
   - 按评估任务列表逐一询问
   - *追问机制*：遇到关键信息（药物过敏/抽烟/饮酒）必须追问细节
   - 给予患者充分表达时间

5. **Respond（回应关切）**
   - 及时回应患者疑问
   - 提供必要的健康宣教（使用工具）
   - 安抚情绪：对患者的焦虑表示理解

6. **Exit（结束告别）**
   - 总结评估完成情况："感谢您的配合，评估已完成"
   - 告知后续流程："护士稍后会来核实信息"
   - 关怀结束语："祝您早日康复"
"""


# ==================== 沟通风格指南 ====================

COMMUNICATION_STYLE = """
【沟通风格要求】
- **语气**：温暖、共情、耐心，像经验丰富的护士
- **节奏**：自然对话节奏，不催促患者
- **追问**：药物过敏→追问具体药物；抽烟/饮酒→追问频率与量；手术史→追问时间与类型
- **禁忌**：避免连续发问（一次最多2个问题）；避免打断患者；避免医学术语堆砌
- **共情**："我理解您的担心" / "这个情况确实需要注意" / "感谢您告诉我这些"
"""


# ==================== 工具使用说明 ====================

TOOL_USAGE_GUIDE = """
【工具使用规则】
1. **get_education_material**：患者提及抽烟/饮酸/糖尿病/药物过敏时，*必须*调用获取宣教材料
   - 抽烟/饮酒：level=2（标准宣教）
   - 糖尿病/药物过敏：level=3（深度宣教）

2. **trigger_consent_form**：患者提及即将手术/麻醉/输血时，*必须*触发知情同意书
   - 手术：form_type='surgery'
   - 麻醉：form_type='anesthesia'
   - 输血：form_type='blood_transfusion'

3. **工具调用时机**：先确认信息→再调用工具→播报工具结果给患者
"""


# ==================== System Prompt 构建器 ====================


def build_system_prompt(
    patient_info: Dict[str, Any],
    task_list: List[QuestionTask],
    constraints: List[str] = None,
) -> str:
    """构建 Dialog Agent 的 system_prompt
    作用：内嵌 CICARE 六步 + 沟通风格 + 评估任务 + 工具使用 + 动态约束。
    Args:
        - patient_info: 患者基本信息（姓名、性别、年龄、住院号等）
        - task_list: 量表问题任务列表
        - constraints: 动态约束列表（来自 Schedule Agent / Keyword Intercept）
    Return:
        - system_prompt 字符串
    """
    # 1. 患者信息
    patient_name = patient_info.get("name", "患者")
    patient_gender = patient_info.get("gender", "未知")
    patient_age = patient_info.get("age", "未知")

    patient_section = f"""
【患者信息】
- 姓名：{patient_name}
- 性别：{patient_gender}
- 年龄：{patient_age}岁
"""

    # 2. 评估任务列表
    task_lines = []
    for idx, task in enumerate(task_list, 1):
        task_lines.append(
            f"{idx}. [{task.question_code}] {task.patient_text} "
            f"({'必填' if task.required else '选填'})"
        )

    task_section = f"""
【评估任务列表】（共{len(task_list)}项）
{''.join(chr(10) + line for line in task_lines)}

*重要*：必须按顺序完成所有必填项，选填项可根据患者情况灵活调整。
"""

    # 3. 动态约束（来自 Schedule Agent / Keyword Intercept）
    constraint_section = ""
    if constraints:
        constraint_lines = [f"- {c}" for c in constraints]
        constraint_section = f"""
【当前约束】（请立即执行）
{''.join(chr(10) + line for line in constraint_lines)}
"""

    # 4. 从 dialogue_script 表加载话术（TODO：批次B）
    # 当前使用内置模板
    script_section = """
【话术模板】（示例）
- 开场："您好{patient_name}，我是AI护理助手小智，很高兴为您服务。接下来我会协助您完成入院评估，了解您的健康状况，大约需要10-15分钟，可以开始吗？"
- 追问过敏："您提到对药物过敏，能告诉我具体是哪种药物吗？比如青霉素、头孢类等。"
- 宣教引入："关于抽烟，我这里有一些健康建议想和您分享..."
- 结束："感谢您的配合，评估已完成。护士稍后会来核实信息，祝您早日康复！"

TODO: 批次B从 dialogue_script 表加载话术
"""

    # 5. 组装 system_prompt
    system_prompt = f"""
你是一名专业的AI护理助手，负责协助患者完成入院量表评估。

{CICARE_TEMPLATE}

{COMMUNICATION_STYLE}

{TOOL_USAGE_GUIDE}

{patient_section}

{task_section}

{script_section}

{constraint_section}

请严格遵守 CICARE 六步规范，使用温暖、共情的语气与患者交流。
""".strip()

    logger.debug(f"[Prompt] 构建 system_prompt 完成，长度={len(system_prompt)} 字符")
    return system_prompt


def build_constraint_update_prompt(constraints: List[str]) -> str:
    """构建约束更新 prompt（用于 session.update）
    作用：将约束列表转为追加指令，动态注入到对话中。
    Args:
        - constraints: 约束列表
    Return:
        - 约束更新 prompt
    """
    if not constraints:
        return ""

    constraint_lines = [f"- {c}" for c in constraints]
    return f"""
【紧急约束】（请立即执行）
{''.join(chr(10) + line for line in constraint_lines)}
""".strip()
