import { describe, expect, it } from 'vitest';
import {
  buildAbilitySummaries,
  buildAssessmentRows,
  buildCgaReportSections,
  formatAssessmentScaleResult,
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
        score_status: 'incomplete',
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
        conclusion: '未完成计分',
        score: '未完成计分',
        riskLevel: '',
      },
    ]);
  });

  it('maps completed scales into the fixed CGA catalogue', () => {
    const sections = buildCgaReportSections(getAssessmentScales(report));
    const physical = sections.find((section) => section.id === 'physical');
    const sleep = sections.find((section) => section.id === 'sleep');

    expect(physical?.rows.find((row) => row.id === 'adl')).toMatchObject({
      item: '自理能力',
      scaleLabel: '日常生活能力评估',
      completed: true,
    });
    expect(sleep?.rows.find((row) => row.id === 'sleep')).toMatchObject({
      item: '睡眠',
      scaleLabel: '睡眠情况',
      result: '未完成计分',
      completed: true,
    });
  });

  it('shows an explicit placeholder when a CGA scale was not performed', () => {
    const sections = buildCgaReportSections(getAssessmentScales(report));
    const mental = sections.find((section) => section.id === 'mental');
    const depression = mental?.rows.find((row) => row.id === 'depression');

    expect(depression).toMatchObject({
      item: '抑郁',
      scaleLabel: '抑郁评分量表（PHQ-9）',
      result: '未进行相关量表',
      completed: false,
    });
  });

  it('formats the real scale conclusion and score without changing the facts', () => {
    const [adl] = getAssessmentScales(report);

    expect(formatAssessmentScaleResult(adl)).toContain('轻度依赖');
    expect(formatAssessmentScaleResult(adl)).toContain('需要关注');
    expect(formatAssessmentScaleResult(adl)).toContain('轻度功能障碍');
    expect(formatAssessmentScaleResult(adl)).toContain('75/100分');
  });

  it('keeps completed scales that are outside the reference CGA catalogue', () => {
    const customReport = {
      sourceSnapshot: {
        assessments: [
          {
            scale_code: 'CUSTOM_SCALE',
            scale_name: '专科自定义量表',
            result_summary: '已完成专科评估',
          },
        ],
      },
    } as unknown as AssessmentReport;

    const sections = buildCgaReportSections(getAssessmentScales(customReport));
    const other = sections.find((section) => section.id === 'other-completed');

    expect(other?.rows).toHaveLength(1);
    expect(other?.rows[0]).toMatchObject({
      scaleLabel: '专科自定义量表',
      result: '已完成专科评估',
      completed: true,
    });
  });
  it('deduplicates matching result summary and score interpretation', () => {
    const scale = {
      scale_code: 'home_environment_screening',
      scale_name: '居家环境筛查表',
      score_status: 'complete' as const,
      result_summary: '得分越低，表明居家环境风险越大',
      scores: [{
        score_name: '总分',
        score_value: 12,
        interpretation: '得分越低，表明居家环境风险越大',
      }],
    };
    const result = formatAssessmentScaleResult(scale);

    expect(result.split('得分越低，表明居家环境风险越大')).toHaveLength(2);
    expect(result).toContain('12分');
  });

  it('keeps a genuine zero but never turns missing score into zero', () => {
    const scale = {
      scale_code: 'home_environment_screening',
      scale_name: '居家环境筛查表',
      score_status: 'complete' as const,
      scores: [{ score_name: '总分', score_value: 0 }],
    };
    expect(formatAssessmentScaleResult(scale)).toContain('0分');

    const incomplete = {
      ...scale,
      score_status: 'incomplete' as const,
      scores: [],
      result_summary: '旧的错误摘要',
    };
    expect(formatAssessmentScaleResult(incomplete)).toBe('未完成计分');
    expect(buildAbilitySummaries([incomplete])[0].score).toBe('未完成计分');
  });

  it('distinguishes an unfinished scored scale from a non-scoring assessment', () => {
    const incomplete = {
      scale_code: 'adl',
      scale_name: 'ADL',
      score_status: 'incomplete' as const,
      scores: [],
    };
    const nonScoring = {
      scale_code: 'admission_assessment',
      scale_name: '入院评估表',
      score_status: 'not_applicable' as const,
      scores: [],
    };
    expect(formatAssessmentScaleResult(incomplete)).toBe('未完成计分');
    expect(formatAssessmentScaleResult(nonScoring)).toBe('已完成评估');

    const physical = buildCgaReportSections([incomplete]).find(
      (section) => section.id === 'physical'
    );
    expect(physical?.rows.find((row) => row.id === 'adl')?.result).toBe('未完成计分');
    expect(physical?.rows.find((row) => row.id === 'fall')?.result).toBe('未进行相关量表');
  });

});
