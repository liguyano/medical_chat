import { describe, expect, it } from 'vitest';
import {
  buildAbilitySummaries,
  buildAssessmentRows,
  getAssessmentScales,
} from '@/lib/assessmentReportView';
import type { AssessmentReport } from '@/lib/types';

const report = {
  sourceSnapshot: {
    assessments: [
      {
        scale_code: 'ADL',
        scale_name: '日常生活能力评估',
        result_summary: '轻度依赖',
        risk_level: '需要关注',
        scores: [
          {
            score_name: 'ADL总分',
            score_value: 75,
            max_score: 100,
            interpretation: '轻度功能障碍',
          },
        ],
        answers: [
          { question: '进食', value: '可独立完成', clinical_score: 10, abnormal: false },
          { question: '床椅转移', value: '需要部分协助', clinical_score: 5, abnormal: true },
        ],
      },
      {
        scale_code: 'SLEEP',
        scale_name: '睡眠情况',
        answers: [
          { question: '总睡眠质量', value: '一般', abnormal: false },
        ],
      },
    ],
  },
} as unknown as AssessmentReport;

describe('assessment report view', () => {
  it('keeps every answered question in the detail table', () => {
    const scales = getAssessmentScales(report);
    const rows = scales.flatMap(buildAssessmentRows);

    expect(rows).toHaveLength(3);
    expect(rows.map((row) => row.question)).toEqual([
      '进食',
      '床椅转移',
      '总睡眠质量',
    ]);
    expect(rows[1]).toMatchObject({
      ability: '日常生活能力评估',
      value: '需要部分协助',
      score: '5',
      status: '需关注',
      abnormal: true,
    });
    expect(rows[2].score).toBe('—');
  });

  it('builds one concise ability summary for each scale', () => {
    const summaries = buildAbilitySummaries(getAssessmentScales(report));

    expect(summaries).toEqual([
      {
        code: 'ADL',
        name: '日常生活能力评估',
        conclusion: '轻度依赖',
        score: 'ADL总分：75 / 100',
        riskLevel: '需要关注',
      },
      {
        code: 'SLEEP',
        name: '睡眠情况',
        conclusion: '已完成评估',
        score: '',
        riskLevel: '',
      },
    ]);
  });
});