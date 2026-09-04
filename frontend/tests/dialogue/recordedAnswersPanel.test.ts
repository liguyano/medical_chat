import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { RecordedAnswersPanel } from '@/components/patient/RecordedAnswersPanel';
import type { StructuredAnswer } from '@/lib/types';

const fields: StructuredAnswer[] = [
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
    recorded: true,
    asked: true,
  },
  {
    questionId: '13',
    questionCode: 'vision_status',
    questionText: '视力情况',
    sourceMessageIds: [],
    extractionConfidence: 0,
    corrected: false,
    recorded: false,
    asked: true,
  },
  {
    questionId: '14',
    questionCode: 'sleep_status',
    questionText: '睡眠情况',
    sourceMessageIds: [],
    extractionConfidence: 0,
    corrected: false,
    recorded: false,
    asked: false,
  },
];

describe('患者桌面评估信息侧栏', () => {
  it('同时展示已记录、已问未记录和还没问，并只给已记录显示最终值', () => {
    const html = renderToStaticMarkup(
      createElement(RecordedAnswersPanel, { answers: fields })
    );

    for (const text of [
      '评估信息',
      '已记录',
      '已问未记录',
      '还没问',
      '排泄情况',
      '有改变',
      '视力情况',
      '睡眠情况',
    ]) {
      expect(html).toContain(text);
    }
    expect(html).not.toContain('冷却');
    expect(html).not.toContain('候选');
  });

  it('没有字段时显示空状态', () => {
    const html = renderToStaticMarkup(
      createElement(RecordedAnswersPanel, { answers: [] })
    );

    expect(html).toContain('暂时没有评估题目信息');
  });
});
