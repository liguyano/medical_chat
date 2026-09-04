# Dialog 思考内容泄漏修复计划

## 1. 问题确认
- [X] 确认患者可见文本中出现模型内部选题/思考内容。
- [X] 确认 TextChatEngine 当前会把 delta.content 原样流式输出并写入历史。
- [X] 确认现有配置已支持 enable_thinking=false，但仍需要协议层兜底。

## 2. 回归测试
- [X] 增加完整 <think>...</think> 过滤测试。
- [X] 增加标签跨多个流式 chunk 拆分时的过滤测试。
- [X] 验证过滤后的 assistant 历史只保存患者可见正文。
- [X] 验证普通文本流式输出不受影响。

## 3. 实现
- [X] 在 TextChatEngine 增加有状态的流式 think 内容过滤器。
- [X] 过滤内容不得进入 SSE、full_text 或 assistant 历史。
- [X] 保持工具调用聚合和普通流式行为不变。

## 4. 验证
- [ ] 运行 Dialog Engine 定向单元测试。
- [X] 核对最终 diff 仅包含计划、测试和文本引擎过滤实现。
