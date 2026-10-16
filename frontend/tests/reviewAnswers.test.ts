import { afterEach, describe, expect, it, vi } from 'vitest';
import { buildReviewAnswers } from '@/lib/reviewAnswers';
import { ApiCareRepository } from '@/lib/repositories/apiRepository';

describe('护士逐题复核答案', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('提交接口保留未修改的最终答案且只发送修改题原因', async () => {
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(async () => new Response(
      JSON.stringify({ code: 'OK', data: null }), { status: 200 }
    ));
    vi.stubGlobal('fetch', fetchMock);
    const result = buildReviewAnswers(['q1', 'q2'], { q1: '原答案', q2: '0' },
      { q1: '修正答案' }, { q1: '护士核实', q2: '已撤销原因' });
    await new ApiCareRepository().submitAssessmentReview({
      taskId: '87', nurseAnswers: result.answers, finalAnswers: result.answers,
      correctionReasons: result.correctionReasons, status: 'confirmed',
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body));
    expect(body.nurse_answers).toEqual({ q1: '修正答案', q2: '0' });
    expect(body.final_answers).toEqual({ q1: '修正答案', q2: '0' });
    expect(body.correction_reasons).toEqual({ q1: '护士核实' });
  });

  it('只修改一题，其余题沿用原答案且只保留该题原因', () => {
    const result = buildReviewAnswers(
      ['q1', 'q2', 'manual'], { q1: '全部自理', q2: '能自理' },
      { q1: '需协助' }, { q1: '护士核实后调整', q2: '旧原因' },
    );
    expect(result.answers).toEqual({ q1: '需协助', q2: '能自理' });
    expect(result.changedIds).toEqual(['q1']);
    expect(result.correctionReasons).toEqual({ q1: '护士核实后调整' });
  });

  it('改回原答案后不再计差异，也不提交残留原因', () => {
    const result = buildReviewAnswers(['q1'], { q1: '自理' }, { q1: '自理' }, { q1: '旧原因' });
    expect(result.changedIds).toEqual([]);
    expect(result.correctionReasons).toEqual({});
  });

  it('未填写的人工题不计差异，人工补答和主动清空原答案属于该题修改', () => {
    expect(buildReviewAnswers(['manual'], {}, { manual: '' }, {}).changedIds).toEqual([]);
    expect(buildReviewAnswers(['manual'], {}, { manual: '已核实' }, {}).changedIds).toEqual(['manual']);
    expect(buildReviewAnswers(['q1'], { q1: '0' }, { q1: '' }, {}).changedIds).toEqual(['q1']);
    expect(buildReviewAnswers(['q1'], { q1: '0' }, {}, {}).answers.q1).toBe('0');
  });
});
