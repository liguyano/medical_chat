import { describe, expect, it } from 'vitest';
import { getManualQuestionDraft, setManualQuestionDraft, patientAnswerValues, getMockPatientQuestionIndices } from '@/lib/manualQuestions';

describe('人工题配置与患者提交', () => {
  const draft = JSON.stringify({ questions: [{ id: 1, patient_text: '测量', derived: false, validation_rule: { min: 0, max: 99 } }] });
  it('勾选以当前 JSON 为准且保留其他校验字段', () => {
    const edited = draft.replace('99', '100');
    const next = setManualQuestionDraft(edited, 1, true);
    expect(JSON.parse(next).questions[0].validation_rule).toEqual({ min: 0, max: 100, manual_required: true });
    expect(getManualQuestionDraft(next).questions[0].validation_rule?.manual_required).toBe(true);
    expect(JSON.parse(setManualQuestionDraft(next, 1, false)).questions[0].validation_rule.manual_required).toBe(false);
  });
  it('无效 JSON 和非法布尔不被复选框覆盖', () => {
    expect(() => getManualQuestionDraft('{')).toThrow();
    expect(() => getManualQuestionDraft(draft.replace('"min":0', '"manual_required":"true"'))).toThrow();
  });
  it('患者草稿和提交剔除人工题、派生题与不在题库的旧值', () => {
    const questions = [{ id: 'a', manualRequired: true }, { id: 'b', derived: false }, { id: 'c', derived: true }];
    expect(patientAnswerValues(questions, { a: '伪造', b: 0, c: 20, old: '旧值' })).toEqual({ b: 0 });
  });
  it('Mock脚本跳过人工问题且不跳过普通问题', () => {
    expect(getMockPatientQuestionIndices([{ id: 'age', manualRequired: true }, { id: 'allergy', manualRequired: true }])).toEqual([0, 3, 4, 5, 6]);
  });
});
