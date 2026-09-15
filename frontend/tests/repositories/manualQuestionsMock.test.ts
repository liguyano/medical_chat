import { describe, expect, it } from 'vitest';
import { MockCareRepository } from '@/lib/repositories/mockRepository';
import { getVisibleQuestions } from '@/lib/mock/assessment';
import type { CareTask } from '@/lib/types';

describe('Mock 人工题配置一致性', () => {
  it('配置勾选传递至问卷和空白AI快照且不产生事件', async () => {
    const repo = new MockCareRepository();
    const scale = await repo.getScaleConfig('1');
    expect(scale.questions.length).toBeGreaterThan(0);
    const original = structuredClone(scale);
    try {
      scale.questions[0].validation_rule = { min: 0, manual_required: true };
      await repo.updateScaleConfig('1', scale);
      expect(getVisibleQuestions({}, ['1'])[0].manualRequired).toBe(true);
      getVisibleQuestions({}, ['1'])[0].manualRequired = false;
      const questionnaire = await repo.getQuestionnaire('unknown');
      expect(questionnaire.questions.find((q) => q.questionCode === scale.questions[0].question_code)?.manualRequired).toBe(true);
      const snapshot = await repo.getDialogueSnapshot({ id: 'new', scaleIds: ['1'] } as CareTask);
      expect(snapshot.answers).toContainEqual(expect.objectContaining({ manualRequired: true, questionCode: scale.questions[0].question_code }));
      expect(snapshot.answers[0].answerText).toBeUndefined();
      expect(snapshot.events).toEqual([]);
    } finally {
      await repo.updateScaleConfig('1', original);
    }
  });
});
