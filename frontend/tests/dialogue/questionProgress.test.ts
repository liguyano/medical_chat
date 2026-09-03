import { describe, expect, it } from 'vitest';
import { mapQuestionProgress } from '@/lib/api/mappers';
import { createQuestionProgressResource } from '@/lib/dialogue/questionProgress';

const dto = {
  session_id: 'SESSION-1', current: 1, total: 3, turn_number: 4,
  active_question_id: 12, candidate_question_ids: [13],
  questions: [
    { question_id: 11, question_code: 'A', question_text: '年龄', scale_name: '入院', required: true, status: 'recorded' as const, is_current: false, cooling_until_turn: null },
    { question_id: 12, question_code: 'B', question_text: '过敏史', scale_name: '入院', required: true, status: 'asked' as const, is_current: true, cooling_until_turn: 6 },
    { question_id: 13, question_code: 'C', question_text: '体重', scale_name: '营养', required: true, status: 'unasked' as const, is_current: false, cooling_until_turn: null },
  ],
};

describe('题目进度映射和刷新边界', () => {
  it('转换所有题目ID，保留真实答案计数和三种状态', () => {
    expect(mapQuestionProgress(dto)).toMatchObject({
      sessionId: 'SESSION-1', current: 1, total: 3,
      activeQuestionId: '12', candidateQuestionIds: ['13'],
      questions: [{ questionId: '11', status: 'recorded' }, { questionId: '12', status: 'asked', isCurrent: true }, { questionId: '13', status: 'unasked' }],
    });
    expect(mapQuestionProgress({ ...dto, active_question_id: null }).activeQuestionId).toBeNull();
  });

  it('后发请求优先，旧请求迟到不能回退快照', async () => {
    const pending: Array<(value: ReturnType<typeof mapQuestionProgress>) => void> = [];
    const resource = createQuestionProgressResource({ getQuestionProgress: () => new Promise((resolve) => pending.push(resolve)) }, 'SESSION-1');
    const first = resource.refresh();
    const second = resource.refresh();
    pending[1](mapQuestionProgress(dto));
    await second;
    pending[0](mapQuestionProgress({ ...dto, current: 0 }));
    await first;
    expect(resource.getSnapshot().data?.current).toBe(1);
  });

  it('跨会话响应不显示，取消后不再更新', async () => {
    let resolve!: (value: ReturnType<typeof mapQuestionProgress>) => void;
    const resource = createQuestionProgressResource({ getQuestionProgress: () => new Promise((done) => { resolve = done; }) }, 'SESSION-2');
    const request = resource.refresh();
    resolve(mapQuestionProgress(dto));
    await request;
    expect(resource.getSnapshot().data).toBeNull();
    expect(resource.getSnapshot().error).toBeTruthy();
    const next = resource.refresh();
    resource.cancel();
    const before = resource.getSnapshot();
    resolve(mapQuestionProgress({ ...dto, session_id: 'SESSION-2' }));
    await next;
    expect(resource.getSnapshot()).toBe(before);
  });

  it('刷新失败保留带错误提示的旧快照，不制造完成进度', async () => {
    let fail = false;
    const resource = createQuestionProgressResource({ getQuestionProgress: async () => {
      if (fail) throw new Error('offline');
      return mapQuestionProgress(dto);
    } }, 'SESSION-1');
    await resource.refresh();
    fail = true;
    await resource.refresh();
    expect(resource.getSnapshot()).toMatchObject({ data: { current: 1 }, error: '进度暂时无法更新，请稍后重试。' });
  });

  it('低频轮询不取消正在等待的请求，慢网络仍可显示结果', async () => {
    let resolve!: (value: ReturnType<typeof mapQuestionProgress>) => void;
    const resource = createQuestionProgressResource({ getQuestionProgress: () => new Promise((done) => { resolve = done; }) }, 'SESSION-1');
    const request = resource.refresh();
    const firstResolve = resolve;
    await resource.refresh(true);
    expect(resolve).toBe(firstResolve);
    resolve(mapQuestionProgress(dto));
    await request;
    expect(resource.getSnapshot().data?.current).toBe(1);
  });
});
