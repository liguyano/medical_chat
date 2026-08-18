# 患者对话进度与 AgentLoop 代码审查

## 审查结论

本次问题 2、4、5 的核心链路已修复，问题 1 按用户要求不再修改，问题 3 重启后未复现且保留幂等保护。

## 关键审查发现与处理

1. 原 Dialog 按 Task-todo 下标结束，会在量表字段问完或固定轮数达到时提前完成；现改为 `AssessmentAnswer` 结构化进度驱动。
2. 空文本、空选项和 AI 抽取置信度低于 `0.6` 的答案不得推进完成；布尔 `False`、数值 `0` 和有效选项仍是合法答案。
3. 原完成流程先提交数据库完成状态，再生成 CICARE Exit；现改为先刷新进度、生成并保存结束语，再提交完成状态和发布 `SessionEndEvent`。
4. 患者答案后的 Dialog、Schedule、Extraction 改为独立 Celery 投递；后台失败和重试不再阻塞 Dialog。
5. Schedule prepare 生成 Redis 可恢复 Task-todo，Dialog 首问只消费该计划；同一 `question_code` 跨量表只安排一次。
6. Dialog 提示词按 CICARE 六步重写，要求先回应患者当前内容、只问一个主题、避免字段名复述和模板化共情。

## 验证结果

- 后端单元测试：169 passed。
- 后端 PostgreSQL/Redis 集成测试：19 passed。
- 前端 Vitest：23 passed。
- 前端 lint、typecheck、production build：通过。
- 真实浏览器：患者端首问预热、连续对话、SSE 连接、进度 `0/38 -> 1/38`、控制台错误为空。

## 已知非本次范围

- `get_education_material` 和 `trigger_consent_form` 当前仍是批次 B 占位工具；本次完成了触发规则和提示词约束，没有声称真实宣教资料库已上线。
- 全仓库 Ruff 仍有历史遗留规则告警；本次所有变更文件单独 Ruff 检查通过。
