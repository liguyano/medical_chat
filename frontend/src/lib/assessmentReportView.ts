import type { AssessmentReport } from '@/lib/types';

export interface AssessmentAnswerSnapshot {
  question?: string;
  value?: unknown;
  clinical_score?: number | null;
  abnormal?: boolean;
}

export interface AssessmentScoreSnapshot {
  score_name?: string;
  score_value?: number | string | null;
  max_score?: number | string | null;
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
  assessor_name?: string | null;
  evaluator?: string | null;
  assessed_at?: string | null;
  assessment_time?: string | null;
  submitted_at?: string | null;
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

export interface AssessmentPatientSnapshot {
  name?: string;
  sex?: string;
  age?: number | string | null;
  department?: string;
  ward?: string;
  bed_no?: string;
  inpatient_no?: string;
  diagnosis?: unknown;
}

export interface CgaReportRow {
  id: string;
  item: string;
  scaleLabel: string;
  result: string;
  completed: boolean;
  assessor: string;
  assessedAt: string;
  sourceScale?: AssessmentScaleSnapshot;
}

export interface CgaReportSection {
  id: string;
  title: string;
  rows: CgaReportRow[];
}

interface CgaCatalogItem {
  id: string;
  item: string;
  scaleLabel: string;
  codes?: string[];
  names?: string[];
}

interface CgaCatalogSection {
  id: string;
  title: string;
  items: CgaCatalogItem[];
}

const CGA_CATALOG: CgaCatalogSection[] = [
  {
    id: 'mental',
    title: '精神意识',
    items: [
      {
        id: 'depression',
        item: '抑郁',
        scaleLabel: '抑郁评分量表（PHQ-9）',
        codes: ['phq9', 'phq_9'],
        names: ['PHQ-9', '抑郁评分量表', '患者健康问卷抑郁量表'],
      },
      {
        id: 'delirium',
        item: '谵妄',
        scaleLabel: '谵妄评估（3D-CAM）',
        codes: ['3d_cam', '3dcam', 'delirium_3d_cam'],
        names: ['3D-CAM', '谵妄评估'],
      },
      {
        id: 'anxiety',
        item: '焦虑',
        scaleLabel: '广泛性焦虑自评量表（GAD-7）',
        codes: ['gad7', 'gad_7'],
        names: ['GAD-7', '广泛性焦虑'],
      },
      {
        id: 'mini-cog',
        item: '智力状态',
        scaleLabel: '简易智力状态评估表 Mini-Cog',
        codes: ['mini_cog', 'minicog'],
        names: ['Mini-Cog', '简易智力状态'],
      },
      {
        id: 'mmse',
        item: '认知功能',
        scaleLabel: '简易智能精神状态检查量表（MMSE）',
        codes: ['mmse'],
        names: ['MMSE', '简易智能精神状态', '简易精神状态检查'],
      },
    ],
  },
  {
    id: 'physical',
    title: '躯体功能',
    items: [
      {
        id: 'adl',
        item: '自理能力',
        scaleLabel: 'Barthel 指数 / 日常生活能力（ADL）',
        codes: ['adl', 'barthel'],
        names: ['Barthel', '日常生活能力(ADL)', '日常生活能力（ADL）', '日常生活能力评价表'],
      },
      {
        id: 'iadl',
        item: '工具性日常生活能力',
        scaleLabel: 'Lawton-Brody IADL 量表',
        codes: ['iadl_lawton_brody', 'iadl'],
        names: ['Lawton-Brody', '工具性日常生活活动能力'],
      },
      {
        id: 'swallowing',
        item: '吞咽功能',
        scaleLabel: '洼田饮水试验',
        codes: ['water_swallow_test', 'kubota_water_swallow'],
        names: ['洼田饮水', '吞咽功能'],
      },
      {
        id: 'fall',
        item: '跌倒',
        scaleLabel: '跌倒/坠床风险评估量表',
        codes: ['fall_risk', 'morse', 'morse_fall'],
        names: ['Morse', '跌倒/坠床', '跌倒坠床', '跌倒风险'],
      },
      {
        id: 'tug',
        item: 'TUG',
        scaleLabel: 'TUG“起立-行走”计时测试',
        codes: ['tug', 'timed_up_and_go'],
        names: ['TUG', '起立-行走', '起立行走'],
      },
      {
        id: 'sppb',
        item: '体能状况',
        scaleLabel: 'SPPB 评分细则',
        codes: ['sppb'],
        names: ['SPPB'],
      },
      {
        id: 'grip',
        item: '握力',
        scaleLabel: '握力测量',
        codes: ['grip_strength'],
        names: ['握力测量', '握力'],
      },
      {
        id: 'sarcopenia',
        item: '肌少症',
        scaleLabel: '肌少症评估',
        codes: ['sarcopenia'],
        names: ['肌少症'],
      },
      {
        id: 'vision',
        item: '视力',
        scaleLabel: '视力简易评估表',
        codes: ['simple_vision', 'visual_function'],
        names: ['视力简易评估', '视觉功能简易评估'],
      },
      {
        id: 'hearing',
        item: '听力',
        scaleLabel: '听力简易评估表',
        codes: ['simple_hearing'],
        names: ['听力简易评估'],
      },
    ],
  },
  {
    id: 'geriatric-syndrome',
    title: '老年综合征',
    items: [
      {
        id: 'urinary-incontinence',
        item: '尿失禁',
        scaleLabel: '国际尿失禁咨询委员会尿失禁问卷简表（ICIQ-SF）',
        codes: ['iciq_sf', 'iciq-sf'],
        names: ['ICIQ-SF', '尿失禁咨询委员会'],
      },
      {
        id: 'fecal-incontinence',
        item: '大便失禁',
        scaleLabel: '大便失禁评分（CCF-FIS）',
        codes: ['ccf_fis', 'ccf-fis'],
        names: ['CCF-FIS', '大便失禁评分'],
      },
      {
        id: 'constipation',
        item: '便秘',
        scaleLabel: '便秘症状评估表',
        codes: ['constipation_symptoms'],
        names: ['便秘症状评估', 'Rome III', 'Rome Ⅲ'],
      },
      {
        id: 'pain',
        item: '疼痛',
        scaleLabel: '疼痛强度评估（NRS）',
        codes: ['chronic_pain_nrs', 'pain_nrs'],
        names: ['慢性疼痛数字评定', '疼痛强度评估'],
      },
      {
        id: 'frailty',
        item: '衰弱',
        scaleLabel: 'FRAIL 衰弱量表',
        codes: ['frail'],
        names: ['FRAIL', '衰弱量表'],
      },
    ],
  },
  {
    id: 'pressure',
    title: '压疮风险',
    items: [
      {
        id: 'braden',
        item: '压疮风险',
        scaleLabel: '压疮危险因素（Braden Scale）',
        codes: ['braden_pressure_injury', 'braden'],
        names: ['Braden', '压疮评估', '压疮风险'],
      },
    ],
  },
  {
    id: 'osteoporosis',
    title: '骨质疏松风险',
    items: [
      {
        id: 'osteoporosis',
        item: '骨质疏松风险',
        scaleLabel: '骨质疏松风险评估',
        codes: ['osteoporosis', 'osteoporosis_risk'],
        names: ['骨质疏松风险评估', '骨质疏松风险'],
      },
    ],
  },
  {
    id: 'sleep',
    title: '睡眠',
    items: [
      {
        id: 'sleep',
        item: '睡眠',
        scaleLabel: '睡眠自测 AIS 量表',
        codes: ['athens_insomnia', 'ais', 'sleep'],
        names: ['阿森斯失眠', 'AIS', '睡眠'],
      },
    ],
  },
  {
    id: 'nutrition',
    title: '营养',
    items: [
      {
        id: 'nrs2002',
        item: '营养风险',
        scaleLabel: '营养风险筛查评分简表（NRS2002）',
        codes: ['nrs2002'],
        names: ['NRS2002', '营养风险筛查'],
      },
      {
        id: 'mna-sf',
        item: '营养状态',
        scaleLabel: '微营养评定法简表（MNA-SF）',
        codes: ['mna_sf', 'mna-sf'],
        names: ['MNA-SF', '微营养评定'],
      },
    ],
  },
  {
    id: 'social',
    title: '社会支持',
    items: [
      {
        id: 'family-apgar',
        item: '社会家庭关怀',
        scaleLabel: '家庭关怀评估（APGAR）',
        codes: ['family_apgar', 'apgar'],
        names: ['家庭关怀评估', 'Family APGAR', '家庭功能'],
      },
      {
        id: 'home-environment',
        item: '居家环境',
        scaleLabel: '居家环境筛查表',
        codes: ['home_environment_screening'],
        names: ['居家环境筛查'],
      },
    ],
  },
];

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '未记录';
  if (Array.isArray(value)) return value.map(displayValue).join('、');
  if (typeof value === 'boolean') return value ? '是' : '否';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function displayScore(score: AssessmentScoreSnapshot): string {
  if (score.score_value === null || score.score_value === undefined || score.score_value === '') {
    return '';
  }
  const name = score.score_name ?? '得分';
  const maximum = score.max_score == null || score.max_score === '' ? '' : ` / ${score.max_score}`;
  return `${name}：${score.score_value}${maximum}`;
}

function normalize(value: string | undefined | null): string {
  return (value ?? '')
    .toLowerCase()
    .replace(/[\s（）()【】\[\]{}·・_\-—/\\:：]/g, '');
}

function scaleMatches(scale: AssessmentScaleSnapshot, item: CgaCatalogItem): boolean {
  const code = normalize(scale.scale_code);
  const name = normalize(scale.scale_name);

  if (
    item.codes?.some((candidate) => {
      const normalizedCandidate = normalize(candidate);
      return code === normalizedCandidate;
    })
  ) {
    return true;
  }

  return (
    item.names?.some((candidate) => {
      const normalizedCandidate = normalize(candidate);
      return Boolean(normalizedCandidate) && name.includes(normalizedCandidate);
    }) ?? false
  );
}

function conciseScore(score: AssessmentScoreSnapshot): string {
  if (score.score_value === null || score.score_value === undefined || score.score_value === '') {
    return score.interpretation?.trim() ?? '';
  }

  const value = String(score.score_value);
  const scoreText = /分$/.test(value) ? value : `${value}分`;
  return [score.interpretation?.trim(), scoreText].filter(Boolean).join(' ');
}

export function formatAssessmentScaleResult(scale: AssessmentScaleSnapshot): string {
  const parts = [
    scale.result_summary?.trim(),
    scale.risk_level?.trim(),
    ...(scale.scores ?? []).map(conciseScore),
  ].filter((value): value is string => Boolean(value));

  const uniqueParts = parts.filter(
    (value, index) => parts.findIndex((candidate) => normalize(candidate) === normalize(value)) === index
  );

  return uniqueParts.join('；') || '已完成评估';
}

export function getAssessmentScales(
  report: AssessmentReport
): AssessmentScaleSnapshot[] {
  const value = report.sourceSnapshot.assessments;
  return Array.isArray(value) ? (value as AssessmentScaleSnapshot[]) : [];
}

export function getAssessmentPatient(
  report: AssessmentReport
): AssessmentPatientSnapshot {
  const value = report.sourceSnapshot.patient;
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return value as AssessmentPatientSnapshot;
}

export function buildCgaReportSections(
  scales: AssessmentScaleSnapshot[]
): CgaReportSection[] {
  const usedScaleIndexes = new Set<number>();

  const sections = CGA_CATALOG.map((section) => ({
    id: section.id,
    title: section.title,
    rows: section.items.map((item): CgaReportRow => {
      const scaleIndex = scales.findIndex(
        (scale, index) => !usedScaleIndexes.has(index) && scaleMatches(scale, item)
      );
      const scale = scaleIndex >= 0 ? scales[scaleIndex] : undefined;

      if (scale) usedScaleIndexes.add(scaleIndex);

      return {
        id: item.id,
        item: item.item,
        scaleLabel: scale?.scale_name || item.scaleLabel,
        result: scale ? formatAssessmentScaleResult(scale) : '未进行相关量表',
        completed: Boolean(scale),
        assessor: scale?.assessor_name || scale?.evaluator || '',
        assessedAt:
          scale?.assessed_at || scale?.assessment_time || scale?.submitted_at || '',
        sourceScale: scale,
      };
    }),
  }));

  const unmatchedRows = scales
    .map((scale, index) => ({ scale, index }))
    .filter(({ index }) => !usedScaleIndexes.has(index))
    .map(({ scale, index }): CgaReportRow => ({
      id: `other-${scale.scale_code ?? index}`,
      item: scale.scale_name ?? '其他评估',
      scaleLabel: scale.scale_name ?? '未命名量表',
      result: formatAssessmentScaleResult(scale),
      completed: true,
      assessor: scale.assessor_name || scale.evaluator || '',
      assessedAt: scale.assessed_at || scale.assessment_time || scale.submitted_at || '',
      sourceScale: scale,
    }));

  if (unmatchedRows.length) {
    sections.push({
      id: 'other-completed',
      title: '其他已完成评估',
      rows: unmatchedRows,
    });
  }

  return sections;
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
