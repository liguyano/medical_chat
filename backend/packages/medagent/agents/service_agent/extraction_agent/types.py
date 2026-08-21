"""结构化答案类型契约。

运行时和持久化只允许这些标准值；原始量表导入阶段必须先完成归一化，
不能把供应商或历史数据中的中文/旧类型带入抽取链路。
"""

from typing import Final, Literal

AnswerType = Literal[
    "text",
    "number",
    "boolean",
    "date",
    "single_choice",
    "multiple_choice",
]

STANDARD_ANSWER_TYPES: Final[tuple[str, ...]] = (
    "text",
    "number",
    "boolean",
    "date",
    "single_choice",
    "multiple_choice",
)

# 仅在输入边界将中文/历史原始类型转换为标准类型；转换后的对象不再携带别名。
SOURCE_ANSWER_TYPE_MAP: Final[dict[str, str]] = {
    "text": "text",
    "textarea": "text",
    "long_text": "text",
    "文本": "text",
    "number": "number",
    "integer": "number",
    "decimal": "number",
    "数字": "number",
    "整数": "number",
    "小数": "number",
    "boolean": "boolean",
    "boolean_with_detail": "boolean",
    "boolean_with_quantity": "boolean",
    "布尔": "boolean",
    "date": "date",
    "datetime": "date",
    "日期": "date",
    "日期时间": "date",
    "single_choice": "single_choice",
    "single_choice_with_other": "single_choice",
    "单选": "single_choice",
    "multiple_choice": "multiple_choice",
    "多选": "multiple_choice",
    "grouped_choice": "multiple_choice",
    "multi_choice": "multiple_choice",
    "multi_choice_with_other": "multiple_choice",
    "multi_choice_with_detail": "multiple_choice",
}


def normalize_answer_type(value: str) -> str:
    """在导入/模型响应边界归一化答案类型。"""
    normalized = SOURCE_ANSWER_TYPE_MAP.get(str(value).strip())
    if normalized is None:
        raise ValueError(f"不支持的答案类型: {value!r}")
    return normalized
