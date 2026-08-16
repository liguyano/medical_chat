import type { AssessmentQuestion } from '@/lib/types';

export const prototypeQuestions: AssessmentQuestion[] = [
  {
    id: 'age',
    questionCode: 'AGE',
    sectionId: 'admission',
    sectionName: '入院评估单',
    questionText: '您的年龄是多少？',
    questionType: 'number',
    required: true,
    scored: false,
    derived: false,
    unit: '岁',
    validationRule: { min: 0, max: 120 },
  },
  {
    id: 'height',
    questionCode: 'HEIGHT',
    sectionId: 'nutrition',
    sectionName: 'NRS2002营养风险',
    questionText: '您的身高是多少？',
    questionType: 'number',
    required: true,
    scored: false,
    derived: false,
    unit: 'cm',
    validationRule: { min: 80, max: 230 },
  },
  {
    id: 'weight',
    questionCode: 'WEIGHT',
    sectionId: 'nutrition',
    sectionName: 'NRS2002营养风险',
    questionText: '您目前的体重是多少？',
    questionType: 'number',
    required: true,
    scored: false,
    derived: false,
    unit: 'kg',
    validationRule: { min: 20, max: 250 },
  },
  {
    id: 'food_reduction',
    questionCode: 'FOOD_REDUCTION',
    sectionId: 'nutrition',
    sectionName: 'NRS2002营养风险',
    questionText: '最近一周进食量是否明显减少？',
    questionType: 'single_choice',
    required: true,
    scored: true,
    derived: false,
    options: [
      { optionCode: 'none', optionLabel: '没有减少', clinicalScore: 0 },
      { optionCode: 'slight', optionLabel: '轻度减少', clinicalScore: 1 },
      { optionCode: 'obvious', optionLabel: '明显减少', clinicalScore: 2 },
    ],
  },
  {
    id: 'allergy',
    questionCode: 'ALLERGY',
    sectionId: 'admission',
    sectionName: '入院评估单',
    questionText: '您是否有药物或食物过敏史？',
    questionType: 'single_choice',
    required: true,
    scored: false,
    derived: false,
    options: [
      { optionCode: 'no', optionLabel: '没有' },
      { optionCode: 'yes', optionLabel: '有' },
    ],
  },
  {
    id: 'allergy_detail',
    questionCode: 'ALLERGY_DETAIL',
    sectionId: 'admission',
    sectionName: '入院评估单',
    questionText: '请说明具体过敏物和发生过的反应',
    questionType: 'text',
    required: true,
    scored: false,
    derived: false,
    placeholder: '例如：青霉素过敏，出现皮疹',
    conditionalLogic: {
      showIf: [{ questionId: 'allergy', operator: 'equals', value: 'yes' }],
    },
  },
  {
    id: 'feeding',
    questionCode: 'ADL_FEEDING',
    sectionId: 'adl',
    sectionName: 'ADL日常生活能力',
    questionText: '您目前进食是否需要他人帮助？',
    questionType: 'single_choice',
    required: true,
    scored: true,
    derived: false,
    options: [
      { optionCode: 'independent', optionLabel: '完全独立', clinicalScore: 10 },
      { optionCode: 'partial', optionLabel: '需要部分帮助', clinicalScore: 5 },
      { optionCode: 'dependent', optionLabel: '完全依赖', clinicalScore: 0 },
    ],
  },
  {
    id: 'mobility',
    questionCode: 'ADL_MOBILITY',
    sectionId: 'adl',
    sectionName: 'ADL日常生活能力',
    questionText: '下床或行走时是否需要协助？',
    questionType: 'single_choice',
    required: true,
    scored: true,
    derived: false,
    options: [
      { optionCode: 'independent', optionLabel: '不需要协助', clinicalScore: 15 },
      { optionCode: 'supervision', optionLabel: '需要陪同或搀扶', clinicalScore: 10 },
      { optionCode: 'dependent', optionLabel: '不能独立下床', clinicalScore: 0 },
    ],
  },
  {
    id: 'fall_history',
    questionCode: 'FALL_HISTORY',
    sectionId: 'fall',
    sectionName: '跌倒/坠床风险',
    questionText: '最近一年是否发生过跌倒或坠床？',
    questionType: 'single_choice',
    required: true,
    scored: true,
    derived: false,
    options: [
      { optionCode: 'no', optionLabel: '没有', clinicalScore: 0 },
      { optionCode: 'yes', optionLabel: '有', clinicalScore: 25 },
    ],
  },
  {
    id: 'skin',
    questionCode: 'BRADEN_SKIN',
    sectionId: 'braden',
    sectionName: 'Braden压疮风险',
    questionText: '目前皮肤是否经常潮湿或有破损？',
    questionType: 'single_choice',
    required: true,
    scored: true,
    derived: false,
    options: [
      { optionCode: 'normal', optionLabel: '皮肤完整且干燥', clinicalScore: 4 },
      { optionCode: 'sometimes', optionLabel: '偶尔潮湿或发红', clinicalScore: 2 },
      { optionCode: 'damaged', optionLabel: '已有破损', clinicalScore: 1 },
    ],
  },
  {
    id: 'smoking',
    questionCode: 'SMOKING',
    sectionId: 'admission',
    sectionName: '入院评估单',
    questionText: '您目前是否吸烟？',
    questionType: 'single_choice',
    required: true,
    scored: false,
    derived: false,
    options: [
      { optionCode: 'no', optionLabel: '不吸烟' },
      { optionCode: 'quit', optionLabel: '已经戒烟' },
      { optionCode: 'yes', optionLabel: '仍在吸烟' },
    ],
  },
  {
    id: 'symptoms',
    questionCode: 'SYMPTOMS',
    sectionId: 'admission',
    sectionName: '入院评估单',
    questionText: '请描述目前最主要的不舒服、担心或需要帮助的问题',
    questionType: 'text',
    required: true,
    scored: false,
    derived: false,
    placeholder: '例如：活动后胸闷，担心夜间下床不安全',
  },
];

const scaleSectionMap: Record<string, string> = {
  '1': 'admission',
  '2': 'adl',
  '3': 'nutrition',
  '4': 'braden',
  '5': 'fall',
};

export function getVisibleQuestions(
  answers: Record<string, unknown>,
  scaleIds?: string[]
): AssessmentQuestion[] {
  const allowedSections = scaleIds?.length
    ? new Set(scaleIds.map((scaleId) => scaleSectionMap[scaleId]).filter(Boolean))
    : null;

  return prototypeQuestions.filter((question) => {
    if (allowedSections && (!question.sectionId || !allowedSections.has(question.sectionId))) {
      return false;
    }
    const conditions = question.conditionalLogic?.showIf;
    if (!conditions) return true;
    return conditions.every((condition) => {
      const answer = answers[condition.questionId];
      if (condition.operator === 'equals') return answer === condition.value;
      if (condition.operator === 'not_equals') return answer !== condition.value;
      if (condition.operator === 'contains') {
        return Array.isArray(answer) && answer.includes(String(condition.value));
      }
      if (condition.operator === 'greater_than') return Number(answer) > Number(condition.value);
      if (condition.operator === 'less_than') return Number(answer) < Number(condition.value);
      return true;
    });
  });
}
