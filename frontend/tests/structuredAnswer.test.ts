import { describe, expect, it } from 'vitest';
import {
  getStructuredAnswerDisplayValue,
  getStructuredAnswerEvidenceMessages,
} from '@/lib/structuredAnswer';

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

describe('结构化答案对话依据', () => {
  it('按来源消息编号返回真实患者原话并过滤AI消息', () => {
    const evidence = getStructuredAnswerEvidenceMessages(
      {
        questionId: '1',
        questionCode: 'bowel_change',
        questionText: '排泄改变',
        answerText: '腹泻3-4次/日',
        sourceMessageIds: ['MSG-P-1', 'MSG-AI-1'],
        extractionConfidence: 0.93,
        corrected: false,
      },
      [
        {
          id: '1',
          sessionId: 'S1',
          messageNo: 'MSG-P-1',
          turnNo: 1,
          role: 'patient',
          contentText: '我一天大概拉三四次',
          occurredAt: '2026-08-26T12:00:00Z',
        },
        {
          id: '2',
          sessionId: 'S1',
          messageNo: 'MSG-AI-1',
          turnNo: 1,
          role: 'ai',
          contentText: '请问排泄情况怎么样？',
          occurredAt: '2026-08-26T11:59:00Z',
        },
      ]
    );

    expect(evidence.map((message) => message.contentText)).toEqual([
      '我一天大概拉三四次',
    ]);
  });
});
