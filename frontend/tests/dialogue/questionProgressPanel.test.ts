import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { QuestionProgressPanel } from '@/components/patient/QuestionProgressPanel';
import type { QuestionProgress } from '@/lib/types/questionProgress';

const data: QuestionProgress = {
  sessionId: 'S1', current: 1, total: 2, turnNumber: 4,
  activeQuestionId: '2', candidateQuestionIds: [],
  questions: [
    { questionId: '1', questionCode: 'A', questionText: '年龄', scaleName: '入院评估', required: true, status: 'recorded', isCurrent: false, coolingUntilTurn: null },
    { questionId: '2', questionCode: 'B', questionText: '体重', scaleName: '营养评估', required: true, status: 'asked', isCurrent: true, coolingUntilTurn: 6 },
    { questionId: '3', questionCode: 'C', questionText: '补充说明', scaleName: '入院评估', required: false, status: 'unasked', isCurrent: false, coolingUntilTurn: null },
  ],
};

describe('患者桌面题目进度面板', () => {
  it('按量表展示全量问题、三种状态与当前题，百分比只使用后端必填计数', () => {
    const html = renderToStaticMarkup(createElement(QuestionProgressPanel, { data, error: null, onRetry() {} }));
    for (const text of ['入院评估', '营养评估', '年龄', '体重', '补充说明', '未询问', '已问待确认', '已记录', '当前题']) expect(html).toContain(text);
    expect(html).toContain('aria-valuenow="50"');
    expect(html).toContain('aria-current="step"');
    expect(html).not.toContain('冷却');
  });
  it('未加载不显示虚构计数，失败有重试和旧快照提示', () => {
    const loading = renderToStaticMarkup(createElement(QuestionProgressPanel, { data: null, error: null, onRetry() {} }));
    expect(loading).toContain('正在加载评估进度');
    expect(loading).not.toContain('role="progressbar"');
    const failed = renderToStaticMarkup(createElement(QuestionProgressPanel, { data, error: '进度暂时无法更新', onRetry() {} }));
    expect(failed).toContain('重新加载');
    expect(failed).toContain('上次成功更新');
  });
});
