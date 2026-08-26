import type { InteractionMessage, StructuredAnswer } from '@/lib/types';

/**
 * 返回结构化答案的用户可见值。
 * option code 只用于审计和后端关联，禁止直接展示给患者或医护。
 */
export function getStructuredAnswerDisplayValue(answer: StructuredAnswer): string {
  if (answer.invalid) return '待人工确认';
  if (answer.displayValue?.trim()) return answer.displayValue.trim();
  if (answer.selectedOptionLabels?.length) {
    return answer.selectedOptionLabels.join('、');
  }
  if (answer.selectedOptionValues?.length) {
    return answer.selectedOptionValues.join('、');
  }
  if (answer.answerText?.trim()) return answer.answerText.trim();
  if (answer.answerNumber !== undefined) return String(answer.answerNumber);
  if (answer.answerBoolean !== undefined) return answer.answerBoolean ? '是' : '否';
  return '已记录';
}

/**
 * 根据后端保存的来源消息编号返回真实患者原话。
 * 模型生成的说明不替代原始对话证据。
 */
export function getStructuredAnswerEvidenceMessages(
  answer: StructuredAnswer,
  messages: InteractionMessage[]
): InteractionMessage[] {
  const messageByIdentity = new Map<string, InteractionMessage>();
  messages.forEach((message) => {
    messageByIdentity.set(message.id, message);
    messageByIdentity.set(message.messageNo, message);
  });

  const seen = new Set<string>();
  return answer.sourceMessageIds
    .map((messageId) => messageByIdentity.get(messageId))
    .filter(
      (message): message is InteractionMessage =>
        Boolean(message) && message?.role === 'patient'
    )
    .filter((message) => {
      if (seen.has(message.messageNo)) return false;
      seen.add(message.messageNo);
      return true;
    });
}
