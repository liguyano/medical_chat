'use client';

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import PatientLayout from '@/components/layout/PatientLayout';
import QuestionCard from '@/components/assessment/QuestionCard';
import { Button } from '@/components/shared/Button';
import { Progress } from '@/components/shared/Progress';
import { Badge } from '@/components/shared/Badge';
import type { AssessmentQuestion } from '@/lib/types';
import {
  DocumentTextIcon,
  CheckCircleIcon,
  ArrowRightIcon,
  ArrowLeftIcon,
} from '@heroicons/react/24/outline';

type AnswerValue = string | string[] | number | boolean | null;

// 模拟量表题目数据
const mockQuestions: AssessmentQuestion[] = [
  {
    id: 'Q1',
    questionCode: 'Q1',
    sectionId: 'SEC1',
    sectionName: '基本信息',
    questionText: '您的年龄是多少？',
    questionType: 'number',
    required: true,
    scored: false,
    derived: false,
    displayOrder: 1,
    unit: '岁',
    validationRule: { min: 0, max: 150 },
  },
  {
    id: 'Q2',
    questionCode: 'Q2',
    sectionId: 'SEC1',
    sectionName: '基本信息',
    questionText: '您的性别是？',
    questionType: 'single_choice',
    required: true,
    scored: false,
    derived: false,
    displayOrder: 2,
    options: [
      { optionCode: 'A', optionLabel: '男', displayOrder: 1 },
      { optionCode: 'B', optionLabel: '女', displayOrder: 2 },
    ],
  },
  {
    id: 'Q3',
    questionCode: 'Q3',
    sectionId: 'SEC2',
    sectionName: '过敏史',
    questionText: '您是否有药物过敏史？',
    questionType: 'single_choice',
    required: true,
    scored: true,
    derived: false,
    displayOrder: 3,
    options: [
      { optionCode: 'A', optionLabel: '无', displayOrder: 1, clinicalScore: 0 },
      { optionCode: 'B', optionLabel: '有', displayOrder: 2, clinicalScore: 1 },
    ],
  },
  {
    id: 'Q4',
    questionCode: 'Q4',
    sectionId: 'SEC2',
    sectionName: '过敏史',
    questionText: '如果有过敏史，请详细描述过敏药物及反应：',
    description: '请详细描述您对哪些药物过敏，以及出现过什么样的过敏反应',
    questionType: 'text',
    required: false,
    scored: false,
    derived: false,
    displayOrder: 4,
    placeholder: '例如：青霉素过敏，出现皮疹和呼吸困难',
    conditionalLogic: {
      showIf: [{ questionId: 'Q3', operator: 'equals', value: 'B' }],
    },
  },
  {
    id: 'Q5',
    questionCode: 'Q5',
    sectionId: 'SEC3',
    sectionName: '既往病史',
    questionText: '您是否患有以下慢性疾病？（可多选）',
    questionType: 'multiple_choice',
    required: true,
    scored: false,
    derived: false,
    displayOrder: 5,
    options: [
      { optionCode: 'A', optionLabel: '高血压', displayOrder: 1 },
      { optionCode: 'B', optionLabel: '糖尿病', displayOrder: 2 },
      { optionCode: 'C', optionLabel: '冠心病', displayOrder: 3 },
      { optionCode: 'D', optionLabel: '慢性肾病', displayOrder: 4 },
      { optionCode: 'E', optionLabel: '以上都没有', displayOrder: 5 },
    ],
  },
  {
    id: 'Q6',
    questionCode: 'Q6',
    sectionId: 'SEC4',
    sectionName: '生活习惯',
    questionText: '您是否吸烟？',
    questionType: 'single_choice',
    required: true,
    scored: true,
    derived: false,
    displayOrder: 6,
    options: [
      { optionCode: 'A', optionLabel: '从不吸烟', displayOrder: 1, clinicalScore: 0 },
      { optionCode: 'B', optionLabel: '已戒烟', displayOrder: 2, clinicalScore: 1 },
      { optionCode: 'C', optionLabel: '偶尔吸烟', displayOrder: 3, clinicalScore: 2 },
      { optionCode: 'D', optionLabel: '经常吸烟', displayOrder: 4, clinicalScore: 3 },
    ],
  },
  {
    id: 'Q7',
    questionCode: 'Q7',
    sectionId: 'SEC4',
    sectionName: '生活习惯',
    questionText: '您是否饮酒？',
    questionType: 'single_choice',
    required: true,
    scored: true,
    derived: false,
    displayOrder: 7,
    options: [
      { optionCode: 'A', optionLabel: '从不饮酒', displayOrder: 1, clinicalScore: 0 },
      { optionCode: 'B', optionLabel: '已戒酒', displayOrder: 2, clinicalScore: 1 },
      { optionCode: 'C', optionLabel: '偶尔饮酒', displayOrder: 3, clinicalScore: 2 },
      { optionCode: 'D', optionLabel: '经常饮酒', displayOrder: 4, clinicalScore: 3 },
    ],
  },
  {
    id: 'Q8',
    questionCode: 'Q8',
    sectionId: 'SEC5',
    sectionName: '当前症状',
    questionText: '请描述您目前的主要不适症状：',
    description: '请尽可能详细地描述您的症状、持续时间和严重程度',
    questionType: 'text',
    required: true,
    scored: false,
    derived: false,
    displayOrder: 8,
    placeholder: '例如：胸痛已持续3天，活动后加重...',
  },
];

export default function PatientFormPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const router = useRouter();
  const [answers, setAnswers] = useState<Record<string, AnswerValue>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [currentSection, setCurrentSection] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // 按章节分组题目
  const sections = mockQuestions.reduce((acc, question) => {
    const sectionName = question.sectionName || '其他';
    if (!acc[sectionName]) {
      acc[sectionName] = [];
    }
    acc[sectionName].push(question);
    return acc;
  }, {} as Record<string, AssessmentQuestion[]>);

  const sectionNames = Object.keys(sections);
  const currentQuestions = sections[sectionNames[currentSection]] || [];
  const totalSections = sectionNames.length;

  // 检查题目是否应该显示（条件逻辑）
  const shouldShowQuestion = (question: AssessmentQuestion): boolean => {
    if (!question.conditionalLogic?.showIf) return true;

    return question.conditionalLogic.showIf.every((condition) => {
      const answer = answers[condition.questionId];
      switch (condition.operator) {
        case 'equals':
          return answer === condition.value;
        case 'not_equals':
          return answer !== condition.value;
        case 'contains':
          return Array.isArray(answer) && answer.includes(String(condition.value));
        case 'greater_than':
          return Number(answer) > Number(condition.value);
        case 'less_than':
          return Number(answer) < Number(condition.value);
        default:
          return true;
      }
    });
  };

  const visibleQuestions = currentQuestions.filter(shouldShowQuestion);

  const handleAnswerChange = (questionId: string, value: AnswerValue) => {
    setAnswers((prev) => ({ ...prev, [questionId]: value }));
    // 清除该题目的错误
    if (errors[questionId]) {
      setErrors((prev) => {
        const newErrors = { ...prev };
        delete newErrors[questionId];
        return newErrors;
      });
    }
  };

  const validateCurrentSection = (): boolean => {
    const newErrors: Record<string, string> = {};

    visibleQuestions.forEach((question) => {
      if (question.required) {
        const answer = answers[question.id];
        if (answer === undefined || answer === null || answer === '') {
          newErrors[question.id] = '此题为必填项';
        } else if (Array.isArray(answer) && answer.length === 0) {
          newErrors[question.id] = '请至少选择一项';
        }
      }

      // 数值验证
      if (question.questionType === 'number' && answers[question.id]) {
        const value = Number(answers[question.id]);
        const rules = question.validationRule;
        if (rules?.min !== undefined && value < rules.min) {
          newErrors[question.id] = `数值不能小于 ${rules.min}`;
        }
        if (rules?.max !== undefined && value > rules.max) {
          newErrors[question.id] = `数值不能大于 ${rules.max}`;
        }
      }
    });

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleNext = () => {
    if (!validateCurrentSection()) {
      return;
    }

    if (currentSection < totalSections - 1) {
      setCurrentSection(currentSection + 1);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  const handlePrevious = () => {
    if (currentSection > 0) {
      setCurrentSection(currentSection - 1);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  const handleSubmit = async () => {
    if (!validateCurrentSection()) {
      return;
    }

    setIsSubmitting(true);

    // 模拟提交延迟
    await new Promise((resolve) => setTimeout(resolve, 1500));

    console.log('提交答案:', answers);

    // TODO: 提交到后端
    // 跳转到完成页面
    router.push(`/patient/complete/${taskId}`);
  };

  const progress = Math.round(((currentSection + 1) / totalSections) * 100);

  return (
    <PatientLayout title="入院评估表" showBack onBack={() => router.push('/patient')}>
      <div className="min-h-screen bg-background pb-24">
        {/* 进度头部 */}
        <div className="sticky top-0 z-10 bg-surface border-b border-border p-4">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center space-x-2">
              <DocumentTextIcon className="w-5 h-5 text-primary" />
              <span className="text-sm font-medium text-foreground">
                {sectionNames[currentSection]}
              </span>
            </div>
            <Badge variant="primary" size="sm">
              第 {currentSection + 1} / {totalSections} 部分
            </Badge>
          </div>
          <Progress value={progress} max={100} variant="primary" size="sm" showLabel />
        </div>

        {/* 题目列表 */}
        <div className="p-4 space-y-4">
          {visibleQuestions.map((question) => (
            <QuestionCard
              key={question.id}
              question={question}
              value={answers[question.id]}
              onChange={(value) => handleAnswerChange(question.id, value)}
              error={errors[question.id]}
              animate
            />
          ))}
        </div>

        {/* 底部操作栏 */}
        <div className="fixed bottom-0 left-0 right-0 bg-surface border-t border-border p-4 safe-area-pb">
          <div className="flex items-center space-x-3">
            {currentSection > 0 && (
              <Button variant="outline" onClick={handlePrevious} className="flex-shrink-0">
                <ArrowLeftIcon className="w-4 h-4 mr-1" />
                上一步
              </Button>
            )}

            {currentSection < totalSections - 1 ? (
              <Button onClick={handleNext} className="flex-1">
                下一步
                <ArrowRightIcon className="w-4 h-4 ml-1" />
              </Button>
            ) : (
              <Button
                onClick={handleSubmit}
                loading={isSubmitting}
                className="flex-1"
              >
                <CheckCircleIcon className="w-4 h-4 mr-1" />
                提交评估
              </Button>
            )}
          </div>
        </div>
      </div>
    </PatientLayout>
  );
}
