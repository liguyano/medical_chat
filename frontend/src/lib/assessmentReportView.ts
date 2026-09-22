import type { AssessmentReport } from '@/lib/types';

export interface AssessmentAnswerSnapshot {
  question?: string;
  value?: unknown;
  clinical_score?: number | null;
  abnormal?: boolean;
}

export interface AssessmentScoreSnapshot {
  score_name?: string;
  score_value?: number | null;
  max_score?: number | null;
  risk_level?: string | null;
  interpretation?: string | null;
}

export interface AssessmentScaleSnapshot {
  scale_code?: string;
  scale_name?: string;
  result_summary?: string | null;
  risk_level?: string | null;
  answers?: AssessmentAnswerSnapshot[];
  scores?: AssessmentScoreSnapshot[];
}

export interface AssessmentAbilitySummary {
  code: string;
  name: string;
  conclusion: string;
  score: string;
  riskLevel: string;
}

export interface AssessmentDetailRow {
  id: string;
  ability: string;
  question: string;
  value: string;
  score: string;
  status: string;
  abnormal: boolean;
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '未记录';
  if (Array.isArray(value)) return value.map(displayValue).join('、');
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function displayScore(score: AssessmentScoreSnapshot): string {
  if (score.score_value === null || score.score_value === undefined) return '';
  const name = score.score_name ?? '得分';
  const maximum = score.max_score == null ? '' : ` / ${score.max_score}`;
  return `${name}：${score.score_value}${maximum}`;
}

export function getAssessmentScales(
  report: AssessmentReport
): AssessmentScaleSnapshot[] {
  const value = report.sourceSnapshot.assessments;
  return Array.isArray(value) ? (value as AssessmentScaleSnapshot[]) : [];
}

export function buildAbilitySummaries(
  scales: AssessmentScaleSnapshot[]
): AssessmentAbilitySummary[] {
  return scales.map((scale, index) => ({
    code: scale.scale_code ?? `scale-${index + 1}`,
    name: scale.scale_name ?? '未命名量表',
    conclusion: scale.result_summary || '已完成评估',
    score: (scale.scores ?? []).map(displayScore).filter(Boolean).join('；'),
    riskLevel: scale.risk_level || '',
  }));
}

export function buildAssessmentRows(
  scale: AssessmentScaleSnapshot
): AssessmentDetailRow[] {
  const ability = scale.scale_name ?? '未命名量表';
  return (scale.answers ?? []).map((answer, index) => {
    const abnormal = answer.abnormal === true;
    return {
      id: `${scale.scale_code ?? ability}-${index}`,
      ability,
      question: answer.question ?? '评估项目',
      value: displayValue(answer.value),
      score:
        answer.clinical_score === null || answer.clinical_score === undefined
          ? '—'
          : String(answer.clinical_score),
      status: abnormal ? '需关注' : '已记录',
      abnormal,
    };
  });
}