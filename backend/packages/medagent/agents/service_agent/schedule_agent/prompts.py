"""Schedule Agent 提示词模板
作用：定义偏离检测的 System Prompt 和 User Prompt 模板。
"""

import json
from typing import Any

from .models import QuestionTask

TASK_TODO_SYSTEM_PROMPT = """你是住院护理评估的 Schedule Agent。
你的任务是把医护人员选择的量表字段整理成可执行的 Task-todo，供 Dialog Agent 开展自然问诊。

要求：
1. 保留全部必填、非派生问题，不得删除临床必需项目。
2. 只输出已提供的问题编码，不得虚构字段。
3. 优先按自然护理沟通顺序组织：身份与基本情况、当前不适、生命体征、既往与过敏、生活习惯、功能与风险、护理需求。
   在此基础上将相关生活话题聚集：吃饭与进食协助、走动与活动能力、起居与自理、睡眠与休息、家人陪伴。
   不改变题目含义、时间范围或固定施测要求，不用话题分组省略任何必需事实。
4. 相同问题编码只安排一次对话采集，后端会把同一事实写入多个量表。
5. opening_guidance 应提示 Dialog Agent 按 CICARE 简短开场，然后从第一个话题入口开始，不朗读第一道量表题。
6. 不输出面向患者的诊断结论，不把评分、护理计划或交班内容伪装成患者自述问题。
7. 患者基础信息中的 diagnosis_snapshot 仅用于内部理解疾病背景和安排评估顺序，
   不得把诊断快照作为患者自述，不得向患者宣告诊断结论。
8. 同次生成topic_route，把全部必填编码串成少量生活话题；每个编码归属且仅归属一个话题，不能遗漏或虚构。
   按自然关联安排主题顺序，例如娱乐视听→日常餐食→饭后活动/起身→夜间休息；依实际题目调整，不能套固定主题清单。
9. 每个话题包含topic_id、title、question_codes、entry_question、follow_up_guidance、answer_branches、evidence_rules、transition_to_next。
   entry_question只问一个生活事实，不是复合问句；进餐入口先问最近一顿吃什么或喜欢食物，不能同轮问筷子勺子、协助或能力。
   视听入口先聊节目/游戏等兴趣；睡眠入口先聊晚间生活习惯。固定测试或必要直接核实例外。
   follow_up_guidance描述等患者回答后如何逐次了解动作或经历，不能写成直接能力问卷；每轮至多一个问题、普通回复最多60字。
   answer_branches说明不感兴趣/拒答/回答转向时如何接话；evidence_rules说明哪些信息不能作为答案，以及缺项如何具体澄清。
   transition_to_next描述连接方式，不是固定台词，不假设当前时间；不要用“咱们再聊某评估”充当连接。
   最后话题只描述检查缺项、等待后台确认，不能宣布完成、告别或让患者休息。
10. 路线不能预设每个兴趣都马上转成能力测试；分支必须允许跟随患者刚说的具体经历，不能固定兴趣→餐具→自理三连问。
    不输出量表评分标准或期待答案，不诱导回答、不隐瞒评估用途。
    路线是引导不是固定台词；固定施测/必要直接核实单独安排、保留原句规范。手动医护项目不得要求患者代答。
    每个话题简洁，不重复原题全文；不要从喜欢食物、餐具、做饭推断自理，模糊“好”不能当明确事实。
"""


def build_task_todo_prompt(
    *,
    patient_info: dict[str, Any],
    questions: list[QuestionTask],
) -> str:
    """构建 Schedule Agent 任务规划提示词。"""
    from ..dialog_agent.conversation_scenes import question_conversation_context

    fields = [
        {
            "question_id": item.question_id,
            "question_code": item.question_code,
            "question_name": item.question_name,
            "patient_text": item.patient_text,
            "required": item.required,
            "section_name": item.section_name,
            "scale_code": item.scale_code,
            **question_conversation_context(item),
        }
        for item in questions
        if item.required
    ]
    return (
        "## 患者基础信息\n"
        f"{json.dumps(patient_info, ensure_ascii=False)}\n\n"
        "## 可规划量表字段\n"
        f"{json.dumps(fields, ensure_ascii=False)}\n\n"
        "请严格输出一个 json 对象，字段为 ordered_question_codes、opening_guidance、planning_reason、topic_route；"
        "不要输出 Markdown、解释文字或 json 代码围栏。"
    )


DEVIATION_CHECK_SYSTEM_PROMPT = """你是一个医疗评估调度助手，负责监控 AI 与患者的对话是否按照量表问题进行。

## 你的职责
1. 判断最近的对话是否偏离了量表问题列表
2. 识别对话中是否涉及了量表问题的回答
3. 给出明确的偏离判断（是/否）和原因
4. 根据对话证据识别已经得到患者有效回答的量表问题编码

## 偏离判断标准

### 属于偏离的情况
- 患者询问与量表无关的问题（例如：食堂在哪里、Wi-Fi密码、探视时间）
- AI 回答了量表之外的生活服务类话题，且超过2轮对话
- AI 遗漏必答事实且不再补问，或在尚有缺项时宣告评估完成
- AI 重复提问已经明确回答过的问题
- 会话已开始后重复开场、自我介绍或重新询问是否开始

### 不属于偏离的情况
- AI 使用 CICARE 规则进行开场白、自我介绍（这是必要的流程）
- AI 对患者回答进行追问、澄清或确认（例如：患者说"抽烟"，AI追问"每天多少支"）
- 患者偶尔提及无关话题，但AI及时引导回量表问题
- AI 根据患者实际表达简短共情，再继续相关生活场景

## 重要原则
1. **追问不算偏离**：AI对患者回答进行深入追问是正常的评估流程
2. **共情不算偏离**：AI对患者情绪进行共情回应是符合CICARE规则的
3. **主动健康宣教属于偏离**：当前系统已关闭主动宣教。若 AI 自行展开戒烟、饮酒、
   跌倒预防等健康教育，或尝试调用宣教工具，应判为偏离并建议立即回到待完成量表问题。
4. **首次开场不算偏离**：仅首次身份和目的说明属于必要流程，重复开场需要纠正
5. **只有持续偏离才判断为偏离**：偶尔1-2轮的无关话题不算偏离
6. **话题过渡不算偏离**：围绕吃饭、起居、活动等生活话题自然引出待完成事实，
   或按当前话题先询问相关题目，不因未按列表顺序就判断偏离。不能把场景铺垫标记为已回答，
   不为单纯闲聊放弃必答缺项；患者明确说出的多个事实可以对应多题。
7. **所有普通问题都要融入生活场景**：不能仅进餐场景化，其他项目又恢复量表口吻。
   场景是获得答案的方式，不是提问前的兴趣铺垫；固定施测和紧急核实仍优先。

## 输出格式
请严格按照 JSON 格式输出：
{
  "is_deviation": bool,
  "reason": str,
  "completed_questions": [str],
  "current_focus": str,
  "suggested_action": str
}

字段说明：
- is_deviation: true表示偏离，false表示正常
- reason: 判断理由（简短说明）
- completed_questions: 仅填写有明确患者回答证据的问题编码，不允许猜测
- current_focus: 当前对话焦点是什么
- suggested_action: 如果偏离，建议采取的行动
"""


def build_deviation_check_prompt(
    remaining_tasks: list[QuestionTask],
    dialog_history: list[dict[str, str]],
    turn_number: int,
) -> str:
    """构建偏离检测的User Prompt
    作用：将当前对话历史和待完成任务列表组装成提示词
    Args:
        - remaining_tasks: 待完成的任务列表
        - dialog_history: 对话历史
        - turn_number: 当前对话轮次
    Return:
        - prompt: User Prompt字符串
    """
    # 1. 格式化待完成任务列表
    tasks_text = _format_remaining_tasks(remaining_tasks)

    # 2. 格式化对话历史
    history_text = _format_dialog_history(dialog_history)

    # 3. 组装提示词
    prompt = f"""## 当前评估任务

待完成事实清单（展示顺序不等于提问顺序）：
{tasks_text}

## 最近的对话历史

{history_text}

## 当前对话轮次
第 {turn_number} 轮

## 请判断

1. 分析最近的对话内容
2. 判断 AI 是否偏离了量表问题列表
3. 识别已经获得明确回答的问题编码
4. 严格按照JSON格式输出判断结果

记住：相关场景追问、简短共情和首次开场不算偏离；主动健康宣教已关闭。
纠偏建议只描述内部缺项和生活话题衔接，不提供让患者照答的量表问句，不要求逐题推进。
固定施测原句、规定操作及必要安全说明优先，不得以场景聊天或字数要求改写。

{get_few_shot_examples_text()}
"""

    return prompt


def _format_remaining_tasks(tasks: list[QuestionTask]) -> str:
    """格式化待完成任务列表
    Args:
        - tasks: 任务列表
    Return:
        - formatted: 格式化后的文本
    """
    if not tasks:
        return "（所有问题已完成）"

    lines = []
    for idx, task in enumerate(tasks[:5], 1):  # 只显示前5个待完成问题
        required_mark = "【必答】" if task.required else "【可选】"
        options = "、".join(option.option_label for option in task.options)
        option_text = f"；可选项：{options}" if options else ""
        lines.append(
            f"{idx}. {required_mark} {task.patient_text} (编码: {task.question_code}{option_text})"
        )

    if len(tasks) > 5:
        lines.append(f"... 还有 {len(tasks) - 5} 个问题待完成")

    return "\n".join(lines)


def _format_dialog_history(history: list[dict[str, str]]) -> str:
    """格式化对话历史
    Args:
        - history: 对话历史列表
    Return:
        - formatted: 格式化后的文本
    """
    if not history:
        return "（暂无对话）"

    lines = []
    role_labels = {
        "assistant": "AI",
        "user": "患者",
        "system": "系统",
    }

    for msg in history:
        role = role_labels.get(msg["role"], msg["role"])
        content = msg["content"]
        lines.append(f"{role}: {content}")

    return "\n".join(lines)


# Few-shot 示例（用于提高准确率）
FEW_SHOT_EXAMPLES: list[dict[str, Any]] = [
    {
        "scenario": "正常追问场景",
        "dialog": [
            {"role": "assistant", "content": "您是否吸烟？"},
            {"role": "user", "content": "我抽烟"},
            {"role": "assistant", "content": "请问您每天大概抽多少支烟？"},
            {"role": "user", "content": "大概10支左右"},
        ],
        "expected_output": {
            "is_deviation": False,
            "reason": "AI对患者回答进行合理追问，这是正常的评估流程",
            "completed_questions": ["smoking_status"],
            "current_focus": "吸烟情况详细评估",
            "suggested_action": "无需干预，继续当前评估",
        },
    },
    {
        "scenario": "偏离场景",
        "dialog": [
            {"role": "assistant", "content": "您是否吸烟？"},
            {"role": "user", "content": "食堂在哪里？"},
            {"role": "assistant", "content": "食堂在住院楼一楼，营业时间是早上7点到晚上7点"},
            {"role": "user", "content": "谢谢"},
            {"role": "assistant", "content": "还有其他问题吗？"},
        ],
        "expected_output": {
            "is_deviation": True,
            "reason": "AI回答了与量表无关的生活服务问题，且持续多轮未回到评估",
            "completed_questions": [],
            "current_focus": "生活服务咨询",
            "suggested_action": "简短回应后，从相关生活场景了解尚未明确的吸烟事实，一次只问一个实际问题，不照念原题",
        },
    },
    {
        "scenario": "共情场景",
        "dialog": [
            {"role": "assistant", "content": "请问您最近是否感到疼痛？"},
            {"role": "user", "content": "是的，我很痛苦，不知道什么时候能好"},
            {
                "role": "assistant",
                "content": "听起来很难受。现在的疼痛按0到10分，您会给几分？",
            },
        ],
        "expected_output": {
            "is_deviation": False,
            "reason": "AI进行了共情回应后，及时引导回到量表问题（疼痛评分）",
            "completed_questions": [],
            "current_focus": "疼痛评估",
            "suggested_action": "无需干预，AI表现良好",
        },
    },
]


def get_few_shot_examples_text() -> str:
    """获取Few-shot示例文本
    作用：将示例格式化为可插入提示词的文本
    Return:
        - examples_text: 格式化的示例文本
    """
    lines = ["## 判断示例\n"]

    for idx, example in enumerate(FEW_SHOT_EXAMPLES, 1):
        lines.append(f"### 示例{idx}：{example['scenario']}\n")
        lines.append("对话：")
        dialog: list[dict[str, str]] = example["dialog"]
        for msg in dialog:
            role = "AI" if msg["role"] == "assistant" else "患者"
            lines.append(f"{role}: {msg['content']}")
        lines.append("\n判断结果：")
        lines.append(json.dumps(example["expected_output"], ensure_ascii=False, indent=2))
        lines.append("\n")

    return "\n".join(lines)
