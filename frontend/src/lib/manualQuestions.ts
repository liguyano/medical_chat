import type { AssessmentQuestion, AssessmentScaleConfigDetail, PrototypeAnswerValue } from '@/lib/types';

export function getMockPatientQuestionIndices(questions: Pick<AssessmentQuestion, 'id' | 'manualRequired'>[]): number[] {
  const manualIds = new Set(questions.filter((question) => question.manualRequired).map((question) => question.id));
  return ['ready', 'age', 'allergy', 'mobility', 'fall_history', 'smoking', 'symptoms']
    .flatMap((id, index) => manualIds.has(id) ? [] : [index]);
}

export function getManualQuestionDraft(json: string): AssessmentScaleConfigDetail {
  const draft = JSON.parse(json) as AssessmentScaleConfigDetail;
  if (!Array.isArray(draft.questions)) throw new Error('量表 JSON 缺少题目列表');
  for (const question of draft.questions) {
    const rule = question.validation_rule;
    if (rule !== undefined && rule !== null && (typeof rule !== 'object' || Array.isArray(rule))) {
      throw new Error('题目校验规则必须是 JSON 对象');
    }
    if (rule && Object.hasOwn(rule, 'manual_required') && typeof rule.manual_required !== 'boolean') {
      throw new Error('manual_required 必须为 true 或 false');
    }
  }
  return draft;
}

export function setManualQuestionDraft(json: string, questionId: number, required: boolean): string {
  const draft = getManualQuestionDraft(json);
  const question = draft.questions.find((item) => item.id === questionId);
  if (!question) throw new Error('当前 JSON 中没有此题');
  question.validation_rule = { ...question.validation_rule, manual_required: required };
  return JSON.stringify(draft, null, 2);
}

export function patientAnswerValues(
  questions: (Pick<AssessmentQuestion, 'id' | 'manualRequired'> & Partial<Pick<AssessmentQuestion, 'derived'>>)[],
  answers: Record<string, PrototypeAnswerValue>
): Record<string, PrototypeAnswerValue> {
  return Object.fromEntries(questions
    .filter((question) => !question.manualRequired && !question.derived && answers[question.id] !== undefined)
    .map((question) => [question.id, answers[question.id]]));
}
