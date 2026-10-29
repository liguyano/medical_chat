"""任务话题路线的共享筛选与提示渲染；不推进临床完成状态。"""

import json

from .models import QuestionTask, TopicRouteStep


def render_topic_route(
    route: list[TopicRouteStep], remaining: list[QuestionTask], *, directions_only: bool = False
) -> str:
    """仅暴露仍有缺项的话题，防止路线缓存导致完成问题重问。"""
    allowed = {task.question_code for task in remaining}
    steps = []
    for topic in route:
        codes = [code for code in topic.question_codes if code in allowed]
        if codes:
            if len(codes) == len(topic.question_codes):
                steps.append(topic.model_dump(mode="json"))
            else:
                # 旧示例可能同时涉及已完成编码，不能只改标签后继续暴露。
                from ..dialog_agent.conversation_scenes import question_conversation_context

                steps.append(
                    {
                        "topic_id": topic.topic_id,
                        "title": topic.title,
                        "question_codes": codes,
                        "remaining_guidance": [
                            question_conversation_context(task)
                            for task in remaining
                            if task.question_code in codes
                        ],
                        "resume_guidance": "延续患者当前生活场景，仅澄清剩余事实，不重开已完成话题入口。",
                    }
                )
    if not steps:
        return ""
    if directions_only:
        directions = [
            {
                "topic_id": step["topic_id"],
                "title": step["title"],
                "question_codes": step["question_codes"],
                "connection": step.get("transition_to_next", "延续当前场景，仅了解剩余事实"),
            }
            for step in steps
        ]
        return (
            "\n【创建任务时生成的话题路线】仅作衔接参考，不是问句顺序；事实范围只见唯一剩余清单。\n"
            + json.dumps(directions, ensure_ascii=False)
        )
    return (
        "\n【创建任务时生成的话题路线】\n"
        "先围绕当前相关话题展开，只有没有相关缺项时再沿路线自然换话题；患者主动换话题可灵活跟随。"
        "入口和分支是参考，不逐句照读，不对每题重开兴趣调查。只能收集各话题列出的剩余编码，"
        "已明确回答不重复问；同一话题含已完成事实时跳过对应追问示例。固定施测原句和安全核实优先。"
        "每轮只问一个实际问题，用短句，不显示路线、内部编码或旁白。路线走完不等于评估完成，仍须系统确认。\n"
        + json.dumps(steps, ensure_ascii=False)
    )
