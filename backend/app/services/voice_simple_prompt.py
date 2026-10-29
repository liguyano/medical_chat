"""实时语音专用的最小问题输入，抽取与正式完成留给后台。"""

import json

from medagent.agents.service_agent.schedule_agent import QuestionTask


def build_voice_question_prompt(patient_info: dict, questions: list[QuestionTask]) -> str:
    patient = {key: patient_info[key] for key in ("name", "age", "gender") if key in patient_info}
    items = [
        {
            "question_id": q.question_id,
            "question": q.patient_text or q.question_name,
            "options": [
                {"label": o.option_label, "value": o.option_value}
                for o in getattr(q, "options", [])
            ],
        }
        for q in questions
    ]
    return (
        "你是AI护理助手，通过对话了解患者护理需要。结合已经说过的内容，自主决定问题顺序和问法，"
        "自然简短地交流，避免反复问同一件事；不猜测患者没说出的事实。"
        "题目中的时间范围、必要安全核实和规定测试原句/操作必须保留。患者可以暂停或拒答。\n"
        + "【患者称呼信息】"
        + json.dumps(patient, ensure_ascii=False)
        + "\n【实时语音剩余评估范围】以下是本次需要了解的全部问题，仅此一份：\n"
        + json.dumps(items, ensure_ascii=False)
        + "\n后台会边聊边提取答案，无需逐题等待或报分。你认为问题已经聊完时，调用"
        "request_assessment_finish让后台核验；只有completed=true才结束。若后台返回缺项，"
        "自行结合上下文补充了解这些缺项，不重新开始整套评估。"
    )
