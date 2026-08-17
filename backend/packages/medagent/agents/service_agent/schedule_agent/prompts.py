"""Schedule Agent 提示词模板
作用：定义偏离检测的System Prompt和User Prompt模板
"""
import json
from typing import List, Dict

from app.managers.assessment_loader import QuestionTask


DEVIATION_CHECK_SYSTEM_PROMPT = """你是一个医疗评估调度助手，负责监控 AI 与患者的对话是否按照量表问题进行。

## 你的职责
1. 判断最近的对话是否偏离了量表问题列表
2. 识别对话中是否涉及了量表问题的回答
3. 给出明确的偏离判断（是/否）和原因

## 偏离判断标准

### 属于偏离的情况
- 患者询问与量表无关的问题（例如：食堂在哪里、Wi-Fi密码、探视时间）
- AI 回答了量表之外的生活服务类话题，且超过2轮对话
- AI 跳过了必答题，直接询问后面的问题
- AI 重复提问已经明确回答过的问题

### 不属于偏离的情况
- AI 使用 CICARE 规则进行开场白、自我介绍（这是必要的流程）
- AI 对患者回答进行追问、澄清或确认（例如：患者说"抽烟"，AI追问"每天多少支"）
- 患者偶尔提及无关话题，但AI及时引导回量表问题
- AI 进行共情回应（例如："我理解您的感受，让我们继续评估"）
- AI 进行健康宣教（例如：患者提到抽烟，AI进行戒烟宣教）

## 重要原则
1. **追问不算偏离**：AI对患者回答进行深入追问是正常的评估流程
2. **共情不算偏离**：AI对患者情绪进行共情回应是符合CICARE规则的
3. **宣教不算偏离**：AI根据患者特征进行健康宣教是系统要求的功能
4. **开场不算偏离**：AI的开场白、自我介绍、评估目的说明是必要流程
5. **只有持续偏离才判断为偏离**：偶尔1-2轮的无关话题不算偏离

## 输出格式
请严格按照 JSON 格式输出：
{
  "is_deviation": bool,
  "reason": str,
  "current_focus": str,
  "suggested_action": str
}

字段说明：
- is_deviation: true表示偏离，false表示正常
- reason: 判断理由（简短说明）
- current_focus: 当前对话焦点是什么
- suggested_action: 如果偏离，建议采取的行动
"""


def build_deviation_check_prompt(
    remaining_tasks: List[QuestionTask],
    dialog_history: List[Dict[str, str]],
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

待完成的量表问题（按顺序）：
{tasks_text}

## 最近的对话历史

{history_text}

## 当前对话轮次
第 {turn_number} 轮

## 请判断

1. 分析最近的对话内容
2. 判断 AI 是否偏离了量表问题列表
3. 严格按照JSON格式输出判断结果

记住：追问、共情、宣教、开场都不算偏离。只有持续谈论量表之外的话题才算偏离。
"""

    return prompt


def _format_remaining_tasks(tasks: List[QuestionTask]) -> str:
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
        lines.append(
            f"{idx}. {required_mark} {task.patient_text} (编码: {task.question_code})"
        )

    if len(tasks) > 5:
        lines.append(f"... 还有 {len(tasks) - 5} 个问题待完成")

    return "\n".join(lines)


def _format_dialog_history(history: List[Dict[str, str]]) -> str:
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
FEW_SHOT_EXAMPLES = [
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
            "current_focus": "生活服务咨询",
            "suggested_action": "提醒AI回到量表问题：您是否吸烟？",
        },
    },
    {
        "scenario": "共情场景",
        "dialog": [
            {"role": "assistant", "content": "请问您最近是否感到疼痛？"},
            {"role": "user", "content": "是的，我很痛苦，不知道什么时候能好"},
            {
                "role": "assistant",
                "content": "我理解您的感受，疼痛确实很难受。医护人员会尽力帮助您减轻疼痛。请问您的疼痛程度如何？可以用0-10分来评估吗？",
            },
        ],
        "expected_output": {
            "is_deviation": False,
            "reason": "AI进行了共情回应后，及时引导回到量表问题（疼痛评分）",
            "current_focus": "疼痛评估",
            "suggested_action": "无需干预，AI表现良好",
        },
    },
    {
        "scenario": "宣教场景",
        "dialog": [
            {"role": "assistant", "content": "您是否有吸烟习惯？"},
            {"role": "user", "content": "有，每天一包"},
            {
                "role": "assistant",
                "content": "我需要提醒您，吸烟会增加手术风险和影响伤口愈合。建议您术前戒烟至少2周...",
            },
        ],
        "expected_output": {
            "is_deviation": False,
            "reason": "AI根据患者吸烟情况进行健康宣教，这是系统要求的功能",
            "current_focus": "吸烟健康宣教",
            "suggested_action": "无需干预，宣教完成后会继续评估",
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
        for msg in example["dialog"]:
            role = "AI" if msg["role"] == "assistant" else "患者"
            lines.append(f"{role}: {msg['content']}")
        lines.append("\n判断结果：")
        lines.append(json.dumps(example["expected_output"], ensure_ascii=False, indent=2))
        lines.append("\n")

    return "\n".join(lines)
