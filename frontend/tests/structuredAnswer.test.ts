import { describe, expect, it } from 'vitest';
import { getStructuredAnswerDisplayValue } from '@/lib/structuredAnswer';

describe('结构化答案展示值', () => {
  it('优先使用真实量表值而不是 option code', () => {
    expect(
      getStructuredAnswerDisplayValue({
        questionId: '1',
        questionCode: 'smoking_years',
        questionText: '抽烟烟龄',
        selectedOptions: ['option_3'],
        selectedOptionLabels: ['10年以上'],
        displayValue: '10年以上',
        sourceMessageIds: ['MSG-1'],
        extractionConfidence: 0.95,
        corrected: false,
      })
    ).toBe('10年以上');
  });

  it('旧数据没有真实值时不向用户暴露内部编码', () => {
    expect(
      getStructuredAnswerDisplayValue({
        questionId: '1',
        questionCode: 'smoking_years',
        questionText: '抽烟烟龄',
        selectedOptions: ['option_3'],
        sourceMessageIds: [],
        extractionConfidence: 0.8,
        corrected: false,
      })
    ).toBe('已记录');
  });
});
