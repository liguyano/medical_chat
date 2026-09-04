import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { RecordedAnswersPanel } from '@/components/patient/RecordedAnswersPanel';
import type { StructuredAnswer } from '@/lib/types';

const answers: StructuredAnswer[] = [
  {
    questionId: '12',
    questionCode: 'bowel_change',
    questionText: '排泄情况',
    selectedOptions: ['yes'],
    selectedOptionLabels: ['有改变'],
    displayValue: '有改变',
    sourceMessageIds: ['MSG-12'],
    extractionConfidence: 0.93,
    corrected: false,
  },
  {
    questionId: '13',
    questionCode: 'vision_status',
    questionText: '视力情况',
    answerText: '看远处有点模糊',
    sourceMessageIds: ['MSG-13'],
    extractionConfidence: 0.88,
    corrected: false,
  },
];

describe('患者桌面已记录信息侧栏', () => {
  it('展示AI已经实际写入的题目和值，不展示候选题或冷却状态', () => {
    const html = renderToStaticMarkup(
      createElement(RecordedAnswersPanel, { answers })
    );

    for (const text of ['已记录信息', '排泄情况', '有改变', '视力情况', '看远处有点模糊']) {
      expect(html).toContain(text);
    }
    expect(html).not.toContain('候选');
    expect(html).not.toContain('冷却');
  });

  it('没有结构化答案时显示空状态', () => {
    const html = renderToStaticMarkup(
      createElement(RecordedAnswersPanel, { answers: [] })
    );

    expect(html).toContain('暂时还没有已记录信息');
  });
});
