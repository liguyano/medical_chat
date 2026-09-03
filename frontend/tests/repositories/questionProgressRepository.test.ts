import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiCareRepository } from '@/lib/repositories/apiRepository';
import { MockCareRepository } from '@/lib/repositories/mockRepository';
import { useChatStore } from '@/lib/stores/useChatStore';

describe('题目进度仓储', () => {
  afterEach(() => vi.unstubAllGlobals());
  it('通过会话权限路径加载并映射数据', async () => {
    const fetchMock = vi.fn<typeof fetch>(async () => new Response(JSON.stringify({ code: 'OK', message: '成功', data: {
      session_id: 'S/1', current: 0, total: 1, turn_number: 0,
      active_question_id: null, candidate_question_ids: [10], questions: [],
    } }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    vi.stubGlobal('fetch', fetchMock);
    const result = await new ApiCareRepository().getQuestionProgress('S/1');
    expect(result).toMatchObject({ sessionId: 'S/1', candidateQuestionIds: ['10'], current: 0 });
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/dialog/S%2F1/question-progress');
  });
  it('Mock按真实关联区分已问和已记录，不计无效答案', async () => {
    const original = useChatStore.getState();
    const base = Object.values(original.sessions)[0];
    useChatStore.setState({ sessions: { ...original.sessions, 'PROGRESS-TEST': {
      ...base, id: 'PROGRESS-SESSION', messages: [{ ...base.messages[0], role: 'ai', relatedQuestionIds: ['age'] }],
    } }, structuredAnswers: { ...original.structuredAnswers, 'PROGRESS-TEST': [{
      questionId: 'age', questionCode: 'AGE', questionText: '年龄', answerNumber: 42,
      invalid: true, sourceMessageIds: [], extractionConfidence: 0.9, corrected: false,
    }] } });
    try {
      const result = await new MockCareRepository().getQuestionProgress('PROGRESS-SESSION');
      expect(result.questions.find((question) => question.questionId === 'age')).toMatchObject({ status: 'asked', isCurrent: true });
      expect(result.current).toBe(0);
    } finally {
      useChatStore.setState({ sessions: original.sessions, structuredAnswers: original.structuredAnswers });
    }
  });
});
