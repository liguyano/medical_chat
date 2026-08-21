import type { StructuredAnswer } from '@/lib/types';

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
