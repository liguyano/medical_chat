"""提示词工程
作用：构建 system_prompt、user_prompt，生成对话摘要，提供 Few-shot 示例
"""

import json


def build_system_prompt(scale_version: dict, questions: list[dict]) -> str:
    """构建系统提示词
    作用：定义字段抽取任务的核心原则、量表信息、输出格式
    Args:
        - scale_version: 量表版本信息 {"scale_name": "...", "version_code": "..."}
        - questions: 问题列表
          [{"question_id": 101, "question_code": "...", "answer_type": "...", ...}]
    Return:
        - system_prompt 文本
    """
    questions_schema = [
        {
            "question_id": q["question_id"],
            "question_code": q["question_code"],
            "question_text": q["question_text"],
            "answer_type": q["answer_type"],
            "options": q.get("options", []),
            "scoring_rules": q.get("scoring_rules", {}),
            "required": q.get("required", False),
        }
        for q in questions
    ]

    return f"""你是一个专业的护理评估字段抽取专家。\
你的任务是从患者与AI的对话中，准确抽取出量表问题的结构化答案。

## 核心原则
1. **忠实原文**：只抽取患者明确说过的内容，不推测、不脑补
2. **多轮综合**：患者可能分多轮回答同一问题（如追问后补充），需综合所有相关对话
3. **置信度标注**：每个字段必须给出抽取可信度（0.0-1.0）
4. **来源追溯**：记录答案来自哪几条对话消息（message_id）
5. **增量更新**：如果历史字段已有答案，新对话纠正时更新并降低置信度；新对话补充细节时提高置信度

## 量表信息
量表名称：{scale_version.get("scale_name", "未知量表")}
量表版本：{scale_version.get("version_code", "v1.0")}

## 问题定义（JSON格式）
{json.dumps(questions_schema, ensure_ascii=False, indent=2)}

## 输出格式（严格遵守JSON Schema）
The response must be a valid json object and must not contain markdown or explanatory text.
{{
  "extracted_answers": [
    {{
      "question_id": 101,
      "question_code": "smoking_status",
      "answer_type": "single_choice",
      "answer_value": "吸烟",  // 文本/数字/布尔/日期
      "selected_option_codes": ["smoking_yes"],  // 单选/多选使用
      "extra_inputs": {{"frequency": 15, "unit": "支/天"}},  // 附加输入
      "clinical_score": 2.0,
      "extraction_confidence": 0.92,
      "source_message_ids": ["MSG-301", "MSG-302"],
      "reasoning": "患者在第5轮明确说'我抽烟'，第6轮补充'每天15支左右'"
    }}
  ],
  "overall_confidence": 0.85,
  "missing_questions": [102, 103],  // 尚未问到的题目
  "ambiguous_questions": [104]  // 回答不清晰的题目
}}

## 重要提示
- 如果历史抽取字段已有答案，且新对话**纠正**了该答案（如"不抽烟了" vs "抽烟"），\
请更新答案并降低置信度
- 如果新对话**补充**了细节（如"每天15支" 补充 "吸烟"），\
请合并到 extra_inputs 并提高置信度
- 纠正 vs 补充的判断标准：纠正=矛盾（互斥），补充=细化（兼容）
- 如果患者回答模糊（"嗯...差不多吧"），请降低置信度并在 reasoning 标注
"""


def build_user_prompt(
    previous_extraction: dict[int, dict],
    history_summary: str,
    new_dialog: list[dict],
) -> str:
    """构建用户提示词
    作用：整合历史抽取字段 + 对话摘要 + 新对话，形成输入
    Args:
        - previous_extraction: 历史抽取字段
          {question_id: {"answer": "...", "confidence": 0.90, "source_turns": [5, 6]}}
        - history_summary: 历史对话摘要（2-3句话）
        - new_dialog: 新对话列表 [{"turn": 8, "patient": "...", "ai": "..."}]
    Return:
        - user_prompt 文本
    """
    prompt_parts = []

    # 1. 历史抽取字段
    if previous_extraction:
        prompt_parts.append("## 历史抽取字段（上一次的抽取结果）")
        for question_id, data in previous_extraction.items():
            prompt_parts.append(
                f"- 题目ID {question_id}: {data.get('answer', 'N/A')} "
                f"(类型: {data.get('answer_type', 'unknown')}, "
                f"选项: {data.get('selected_option_codes', [])}, "
                f"置信度: {data.get('confidence', 0.0):.2f}, "
                f"来源轮次: {data.get('source_turns', [])})"
            )
        prompt_parts.append("")

    # 2. 历史对话摘要
    if history_summary:
        prompt_parts.append("## 历史对话摘要")
        prompt_parts.append(history_summary)
        prompt_parts.append("")

    # 3. 新对话
    prompt_parts.append("## 新对话（当前轮）")
    for turn_data in new_dialog:
        turn_num = turn_data.get("turn", "?")
        message_id = turn_data.get("message_id", "")
        patient_text = turn_data.get("patient", "")
        ai_text = turn_data.get("ai_question", turn_data.get("ai", ""))
        prompt_parts.append(f"[轮次{turn_num} | message_id={message_id}]")
        prompt_parts.append(f"护理人员问：{ai_text}")
        prompt_parts.append(f"患者答：{patient_text}")
        prompt_parts.append("")

    # 4. 任务指令
    prompt_parts.append("## 任务")
    prompt_parts.append(
        "请根据以上信息，抽取或更新量表字段。如果新对话纠正了历史字段，请更新并降低置信度；如果新对话补充了细节，请合并并提高置信度。"
    )

    return "\n".join(prompt_parts)


def get_summarization_prompt(messages: list[dict]) -> str:
    """构建对话摘要提示词
    作用：调用 LLM 将历史对话压缩为 2-3 句话
    Args:
        - messages: 对话列表 [{"turn": 1, "patient": "...", "ai": "..."}, ...]
    Return:
        - 摘要提示词
    """
    dialog_text = "\n".join(
        [
            f"[轮{m['turn']}] 患者：{m.get('patient', '')} | AI：{m.get('ai', '')}"
            for m in messages
        ]
    )

    return f"""请将以下护理评估对话压缩为简短、直接的事实摘要，\
保留关键医疗信息（症状、药物、数值、过敏史等），去除寒暄和重复内容。

## 对话历史
{dialog_text}

## 要求
- 摘要长度：最多 3 句（不超过 180 字）
- 保留关键词：数值（体重、血压）、药物名称、症状描述、吸烟/饮酒史
- 去除寒暄：如"您好"、"谢谢"等
- 明确记录前后矛盾和后续更正，例如：用户历史说没有过敏，后续反问得知青霉素过敏；
- 格式：自然语言，不需要"患者说"等前缀

## 输出示例
"患者自述吸烟20年史，每天约15支；体重65公斤，身高175cm；否认药物过敏。"
"""


# Few-shot 示例（供文档和测试使用）
FEWSHOT_EXAMPLES = {
    "text_field": {
        "input": '[轮3] 患者：我叫张三 | AI：好的，张先生',
        "output": {
            "question_id": 101,
            "question_code": "patient_name",
            "answer_type": "text",
            "answer_value": "张三",
            "extraction_confidence": 0.95,
            "source_message_ids": [301],
            "reasoning": "患者明确说'我叫张三'",
        },
    },
    "number_field": {
        "input": '[轮5] 患者：体重65公斤 | AI：好的，记录了',
        "output": {
            "question_id": 102,
            "question_code": "body_weight",
            "answer_type": "number",
            "answer_value": 65.0,
            "extra_inputs": {"unit": "kg"},
            "extraction_confidence": 0.92,
            "source_message_ids": [305],
            "reasoning": "患者明确说体重65公斤",
        },
    },
    "boolean_field": {
        "input": '[轮7] 患者：没有过敏 | AI：好的',
        "output": {
            "question_id": 103,
            "question_code": "drug_allergy",
            "answer_type": "boolean",
            "answer_value": False,
            "extraction_confidence": 0.98,
            "source_message_ids": [307],
            "reasoning": "患者明确说'没有过敏'",
        },
    },
    "single_choice": {
        "input": '[轮5] 患者：我抽烟 | AI：明白了，请问每天抽多少？',
        "output": {
            "question_id": 104,
            "question_code": "smoking_status",
            "answer_type": "single_choice",
            "selected_option_codes": ["smoking_yes"],
            "clinical_score": 2.0,
            "extraction_confidence": 0.90,
            "source_message_ids": [305],
            "reasoning": "患者明确说'我抽烟'",
        },
    },
    "multiple_choice": {
        "input": '[轮8] 患者：我有糖尿病和高血压 | AI：好的，记录了',
        "output": {
            "question_id": 105,
            "question_code": "chronic_diseases",
            "answer_type": "multiple_choice",
            "selected_option_codes": ["diabetes", "hypertension"],
            "extraction_confidence": 0.95,
            "source_message_ids": [308],
            "reasoning": "患者明确说有糖尿病和高血压",
        },
    },
    "extra_inputs": {
        "input": '[轮5] 患者：我抽烟 | AI：每天多少支？ | [轮6] 患者：每天大概15支',
        "output": {
            "question_id": 104,
            "question_code": "smoking_status",
            "answer_type": "single_choice",
            "selected_option_codes": ["smoking_yes"],
            "extra_inputs": {"frequency": 15, "unit": "支/天"},
            "clinical_score": 2.0,
            "extraction_confidence": 0.92,
            "source_message_ids": [305, 306],
            "reasoning": "患者在轮5说抽烟，轮6补充每天15支",
        },
    },
    "incremental_correction": {
        "previous": {
            "question_id": 104,
            "answer": "吸烟",
            "confidence": 0.90,
            "source_turns": [5, 6],
        },
        "new_dialog": '[轮10] 患者：最近戒烟了，现在不抽了 | AI：很好！',
        "output": {
            "question_id": 104,
            "question_code": "smoking_status",
            "answer_type": "single_choice",
            "selected_option_codes": ["smoking_no"],
            "extra_inputs": {"quit_date": "近期"},
            "extraction_confidence": 0.75,
            "source_message_ids": [310],
            "reasoning": "患者纠正历史信息：从'吸烟'改为'戒烟'",
        },
    },
    "incremental_supplement": {
        "previous": {
            "question_id": 104,
            "answer": "吸烟",
            "confidence": 0.85,
            "source_turns": [5],
        },
        "new_dialog": '[轮6] 患者：每天大概15支 | AI：好的',
        "output": {
            "question_id": 104,
            "question_code": "smoking_status",
            "answer_type": "single_choice",
            "selected_option_codes": ["smoking_yes"],
            "extra_inputs": {"frequency": 15, "unit": "支/天"},
            "clinical_score": 2.0,
            "extraction_confidence": 0.92,
            "source_message_ids": [305, 306],
            "reasoning": "患者补充细节：从'吸烟'细化到'每天15支'",
        },
    },
    "low_confidence": {
        "input": '[轮8] 患者：嗯...差不多吧 | AI：请您再确认一下',
        "output": {
            "question_id": 106,
            "question_code": "exercise_frequency",
            "answer_type": "text",
            "answer_value": "差不多",
            "extraction_confidence": 0.45,
            "source_message_ids": [308],
            "reasoning": "患者回答模糊，需护士确认",
        },
    },
}
