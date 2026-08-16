'use client';

import { useMemo, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import PatientLayout from '@/components/layout/PatientLayout';
import QuestionCard from '@/components/assessment/QuestionCard';
import { Button } from '@/components/shared/Button';
import { Progress } from '@/components/shared/Progress';
import { Badge } from '@/components/shared/Badge';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import { getVisibleQuestions, prototypeQuestions } from '@/lib/mock/assessment';
import type { PrototypeAnswerValue } from '@/lib/types';
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  CheckCircleIcon,
  CloudArrowUpIcon,
  DocumentTextIcon,
} from '@heroicons/react/24/outline';

const EMPTY_FORM_ANSWERS: Record<string, PrototypeAnswerValue> = {};

export default function PatientFormPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const router = useRouter();
  const task = useTaskStore((state) => state.tasks.find((item) => item.id === taskId));
  const formDrafts = useTaskStore((state) => state.formDrafts);
  const answers = formDrafts[taskId] ?? EMPTY_FORM_ANSWERS;
  const saveFormAnswer = useTaskStore((state) => state.saveFormAnswer);
  const submitForm = useTaskStore((state) => state.submitForm);
  const updateTask = useTaskStore((state) => state.updateTask);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [currentSection, setCurrentSection] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const visibleQuestions = useMemo(
    () =>
      getVisibleQuestions(
        answers,
        task?.scaleIds ?? (task?.scaleId ? [task.scaleId] : undefined)
      ),
    [answers, task]
  );
  const sections = useMemo(
    () =>
      visibleQuestions.reduce<Record<string, typeof prototypeQuestions>>((result, question) => {
        const name = question.sectionName ?? '其他';
        result[name] = [...(result[name] ?? []), question];
        return result;
      }, {}),
    [visibleQuestions]
  );
  const sectionNames = Object.keys(sections);
  const safeSectionIndex = Math.min(currentSection, Math.max(sectionNames.length - 1, 0));
  const currentQuestions = sections[sectionNames[safeSectionIndex]] ?? [];
  const requiredQuestions = visibleQuestions.filter((question) => question.required);
  const answeredCount = requiredQuestions.filter((question) => {
    const answer = answers[question.id];
    return Array.isArray(answer) ? answer.length > 0 : answer !== undefined && answer !== null && answer !== '';
  }).length;

  const handleAnswer = (questionId: string, value: PrototypeAnswerValue) => {
    const previousValue = answers[questionId];
    const wasAnswered = Array.isArray(previousValue)
      ? previousValue.length > 0
      : previousValue !== undefined && previousValue !== null && previousValue !== '';
    const nextAnsweredCount = wasAnswered
      ? answeredCount
      : Math.min(answeredCount + 1, requiredQuestions.length);
    saveFormAnswer(taskId, questionId, value);
    setErrors((current) => {
      const next = { ...current };
      delete next[questionId];
      return next;
    });
    updateTask(taskId, {
      taskStatus: 'in_progress',
      progress: { current: nextAnsweredCount, total: requiredQuestions.length },
    });
  };

  const validateSection = () => {
    const nextErrors: Record<string, string> = {};
    currentQuestions.forEach((question) => {
      const answer = answers[question.id];
      if (
        question.required &&
        (answer === undefined ||
          answer === null ||
          answer === '' ||
          (Array.isArray(answer) && answer.length === 0))
      ) {
        nextErrors[question.id] = '此题为必填项';
      }
      if (question.questionType === 'number' && answer !== undefined && answer !== '') {
        const value = Number(answer);
        if (question.validationRule?.min !== undefined && value < question.validationRule.min) {
          nextErrors[question.id] = `数值不能小于 ${question.validationRule.min}`;
        }
        if (question.validationRule?.max !== undefined && value > question.validationRule.max) {
          nextErrors[question.id] = `数值不能大于 ${question.validationRule.max}`;
        }
      }
    });
    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const nextSection = () => {
    if (!validateSection()) return;
    setCurrentSection((value) => Math.min(value + 1, sectionNames.length - 1));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const previousSection = () => {
    setCurrentSection((value) => Math.max(value - 1, 0));
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const submit = async () => {
    if (!validateSection()) return;
    if (answeredCount !== requiredQuestions.length) {
      const firstMissing = requiredQuestions.find((question) => {
        const answer = answers[question.id];
        return answer === undefined || answer === null || answer === '';
      });
      if (firstMissing?.sectionName) {
        setCurrentSection(sectionNames.indexOf(firstMissing.sectionName));
        setErrors({ [firstMissing.id]: '请先完成此必填项' });
      }
      return;
    }
    setIsSubmitting(true);
    await new Promise((resolve) => setTimeout(resolve, 600));
    submitForm(taskId, requiredQuestions.length);
    if (task?.consentRequired) {
      updateTask(taskId, { taskStatus: 'in_progress' });
    }
    const nextPath = task?.consentRequired
      ? `/patient/consent/${taskId}`
      : `/patient/complete/${taskId}`;
    router.push(nextPath);
  };

  if (!task) {
    return (
      <PatientLayout title="传统问卷" showBack>
        <div className="p-6 text-center">任务不存在</div>
      </PatientLayout>
    );
  }

  return (
    <PatientLayout title="传统问卷评估" showBack onBack={() => router.push(`/patient/tasks/${taskId}`)}>
      <div className="min-h-screen bg-background pb-28">
        <div className="sticky top-14 z-40 bg-surface border-b border-border p-4">
          <div className="max-w-xl mx-auto">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <DocumentTextIcon className="w-5 h-5 text-primary" />
                <span className="text-sm font-medium">{sectionNames[safeSectionIndex]}</span>
              </div>
              <Badge variant="primary" size="sm">
                {answeredCount}/{requiredQuestions.length}
              </Badge>
            </div>
            <Progress value={answeredCount} max={requiredQuestions.length} size="sm" />
            <div className="mt-2 flex items-center gap-1 text-xs text-green-700">
              <CloudArrowUpIcon className="w-4 h-4" />
              回答已自动保存，可退出后继续
            </div>
          </div>
        </div>

        <div className="max-w-xl mx-auto p-4 space-y-4">
          {currentQuestions.map((question) => (
            <QuestionCard
              key={question.id}
              question={question}
              value={answers[question.id]}
              onChange={(value) => handleAnswer(question.id, value)}
              error={errors[question.id]}
            />
          ))}
        </div>

        <div className="fixed bottom-0 inset-x-0 z-50 bg-surface border-t border-border p-4 safe-area-pb">
          <div className="max-w-xl mx-auto flex gap-3">
            {safeSectionIndex > 0 && (
              <Button variant="outline" onClick={previousSection}>
                <ArrowLeftIcon className="w-4 h-4 mr-1" />
                上一步
              </Button>
            )}
            {safeSectionIndex < sectionNames.length - 1 ? (
              <Button className="flex-1" onClick={nextSection}>
                下一步
                <ArrowRightIcon className="w-4 h-4 ml-1" />
              </Button>
            ) : (
              <Button className="flex-1" loading={isSubmitting} onClick={submit}>
                <CheckCircleIcon className="w-4 h-4 mr-1" />
                检查并提交
              </Button>
            )}
          </div>
        </div>
      </div>
    </PatientLayout>
  );
}
