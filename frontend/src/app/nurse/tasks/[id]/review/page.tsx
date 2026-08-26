'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import NurseLayout from '@/components/layout/NurseLayout';
import { Card } from '@/components/shared/Card';
import { Badge } from '@/components/shared/Badge';
import { Button } from '@/components/shared/Button';
import { IntegrationStatus } from '@/components/shared/IntegrationStatus';
import { prototypeQuestions } from '@/lib/mock/assessment';
import { careRepository } from '@/lib/repositories';
import { runtimeConfig } from '@/lib/runtime/config';
import { useChatStore } from '@/lib/stores/useChatStore';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import type { AssessmentReview } from '@/lib/types';
import {
  ArrowLeftIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';

function answerText(value: unknown) {
  if (Array.isArray(value)) return value.join('、');
  if (value === true) return '是';
  if (value === false) return '否';
  return value === undefined || value === null ? '' : String(value);
}

export default function NurseReviewPage() {
  const { id: taskId } = useParams<{ id: string }>();
  const router = useRouter();
  const task = useTaskStore((state) => state.tasks.find((item) => item.id === taskId));
  const submittedAnswers = useTaskStore((state) => state.submittedAnswers);
  const formSubmission = submittedAnswers[taskId];
  const existingReview = useTaskStore((state) => state.reviews[taskId]);
  const saveReview = useTaskStore((state) => state.saveReview);
  const structuredAnswers = useChatStore((state) => state.structuredAnswers);
  const aiAnswers = structuredAnswers[taskId];
  const session = useChatStore((state) => state.sessions[taskId]);
  const apiMode = runtimeConfig.dataMode === 'api';
  const [questionnaire, setQuestionnaire] = useState<
    Awaited<ReturnType<typeof careRepository.getQuestionnaire>> | null
  >(null);
  const [questionnaireLoading, setQuestionnaireLoading] = useState(
    apiMode && task?.collectionMode === 'traditional_form'
  );

  useEffect(() => {
    if (!apiMode || !task || task.collectionMode !== 'traditional_form') return;
    const controller = new AbortController();
    void careRepository
      .getQuestionnaire(taskId, controller.signal)
      .then(setQuestionnaire)
      .catch(() => {
        if (!controller.signal.aborted) setQuestionnaire(null);
      })
      .finally(() => {
        if (!controller.signal.aborted) setQuestionnaireLoading(false);
      });
    return () => controller.abort();
  }, [apiMode, task, taskId]);

  const sourceAnswers = useMemo(() => {
    if (apiMode && task?.collectionMode === 'traditional_form' && questionnaire) {
      return Object.fromEntries(
        questionnaire.answers.map((answer) => [
          answer.questionId,
          answer.displayValue ?? answer.selectedOptionLabels.join('、') ?? '',
        ])
      );
    }
    if (task?.collectionMode === 'ai_dialogue') {
      return Object.fromEntries(
        (aiAnswers ?? []).map((answer) => [
          answer.questionId,
          answerText(answer.answerText ?? answer.answerNumber ?? answer.answerBoolean),
        ])
      );
    }
    return Object.fromEntries(
      Object.entries(formSubmission ?? {}).map(([key, value]) => [key, answerText(value)])
    );
  }, [aiAnswers, apiMode, formSubmission, questionnaire, task?.collectionMode]);

  const reviewQuestions = useMemo(() => {
    if (apiMode && task?.collectionMode === 'traditional_form' && questionnaire) {
      return questionnaire.questions.filter((question) =>
        Object.prototype.hasOwnProperty.call(sourceAnswers, question.id)
      );
    }
    if (task?.collectionMode === 'ai_dialogue') {
      return (aiAnswers ?? []).map((answer) => ({
        id: answer.questionId,
        questionText: answer.questionText,
        sectionName: 'AI 对话量表',
      }));
    }
    return prototypeQuestions.filter((question) =>
      Object.prototype.hasOwnProperty.call(sourceAnswers, question.id)
    );
  }, [apiMode, questionnaire, sourceAnswers, task?.collectionMode]);
  const [nurseAnswers, setNurseAnswers] = useState<Record<string, string>>(
    existingReview?.nurseAnswers ?? {}
  );
  const [reasons, setReasons] = useState<Record<string, string>>(
    existingReview?.correctionReasons ?? {}
  );
  const [supplementaryInquiry, setSupplementaryInquiry] = useState(
    existingReview?.supplementaryInquiry ?? ''
  );
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const effectiveNurseAnswers =
    Object.keys(nurseAnswers).length > 0 ? nurseAnswers : sourceAnswers;

  if (!task) {
    return <NurseLayout><Card padding="lg">任务不存在</Card></NurseLayout>;
  }

  if (questionnaireLoading) {
    return <NurseLayout><Card padding="lg">正在加载问卷提交结果…</Card></NurseLayout>;
  }

  const differences = reviewQuestions.filter(
    (question) =>
      effectiveNurseAnswers[question.id] !== sourceAnswers[question.id]
  );

  const persistReview = async (status: AssessmentReview['status']) => {
    const missingReason = differences.find((question) => !reasons[question.id]?.trim());
    if (status === 'confirmed' && missingReason) {
      setError(`请填写“${missingReason.questionText}”的修改原因`);
      return;
    }
    const review: AssessmentReview = {
      taskId,
      nurseAnswers: effectiveNurseAnswers,
      finalAnswers: effectiveNurseAnswers,
      correctionReasons: reasons,
      supplementaryInquiry,
      status,
      reviewedAt: new Date().toISOString(),
    };
    setSubmitting(true);
    try {
      await careRepository.submitAssessmentReview(review);
      saveReview(review);
      if (status === 'confirmed') {
        router.push(`/nurse/tasks/${taskId}/nursing-plan`);
      } else {
        router.push(`/nurse/tasks/${taskId}`);
      }
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : '复核结果保存失败'
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <NurseLayout>
      <div className="mb-5">
        <Link href={`/nurse/tasks/${taskId}`} className="inline-flex items-center gap-2 text-sm text-foreground-muted mb-2">
          <ArrowLeftIcon className="w-4 h-4" />
          返回任务详情
        </Link>
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-3">
          <div>
            <h1 className="text-3xl">护士<span className="text-primary italic">评估复核</span></h1>
            <p className="text-foreground-muted mt-1">
              {task.patientName} · {task.bedNo} · {task.collectionMode === 'ai_dialogue' ? 'AI结构化结果' : '患者问卷提交'}
            </p>
          </div>
          <div className="flex gap-2">
            <IntegrationStatus compact />
            <Badge variant="info">{reviewQuestions.length}项答案</Badge>
            <Badge variant={differences.length ? 'warning' : 'success'}>{differences.length}项差异</Badge>
          </div>
        </div>
      </div>

      {session?.aiSummary && (
        <Card padding="md" className="mb-4 border-primary/20 bg-primary-tint">
          <p className="text-xs text-primary font-medium mb-1">AI会话总结</p>
          <p className="text-sm">{session.aiSummary}</p>
        </Card>
      )}

      {questionnaire?.scores.length ? (
        <Card padding="md" className="mb-4">
          <p className="text-xs text-foreground-muted mb-2">规则计分结果</p>
          <div className="flex flex-wrap gap-2">
            {questionnaire.scores.map((score) => (
              <Badge key={score.scaleId} variant="info">
                {score.scaleName}：{score.totalScore ?? '—'} 分
                {score.resultSummary ? ` · ${score.resultSummary}` : ''}
              </Badge>
            ))}
          </div>
        </Card>
      ) : null}

      <div className="space-y-4">
        {reviewQuestions.map((question) => {
          const source = sourceAnswers[question.id] ?? '';
          const nurse = effectiveNurseAnswers[question.id] ?? '';
          const different = source !== nurse;
          const sourceMessages = aiAnswers?.find((answer) => answer.questionId === question.id)?.sourceMessageIds;
          return (
            <Card key={question.id} padding="lg" className={different ? 'border-amber-300' : ''}>
              <div className="flex items-start justify-between gap-3 mb-4">
                <div>
                  <p className="text-xs text-foreground-muted">{question.sectionName}</p>
                  <h2 className="font-semibold mt-1">{question.questionText}</h2>
                </div>
                <Badge variant={different ? 'warning' : 'success'} size="sm">
                  {different ? '存在修正' : '一致'}
                </Badge>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="rounded-xl bg-surface-secondary p-4">
                  <p className="text-xs text-foreground-muted">
                    {task.collectionMode === 'ai_dialogue' ? 'AI结构化答案' : '患者提交答案'}
                  </p>
                  <p className="font-medium mt-2">{source || '未采集'}</p>
                  {sourceMessages?.length && (
                    <Link
                      href={`/nurse/monitor/${taskId}`}
                      className="text-xs text-primary mt-2 inline-block"
                    >
                      查看证据消息 {sourceMessages.join(', ')}
                    </Link>
                  )}
                </div>
                <div>
                  <label className="text-xs text-foreground-muted">护士独立确认答案</label>
                  <input
                    value={nurse}
                    onChange={(event) =>
                      setNurseAnswers((current) => ({
                        ...current,
                        [question.id]: event.target.value,
                      }))
                    }
                    className="w-full mt-2 rounded-xl border border-border bg-surface px-4 py-3"
                  />
                  {different && (
                    <input
                      value={reasons[question.id] ?? ''}
                      onChange={(event) =>
                        setReasons((current) => ({
                          ...current,
                          [question.id]: event.target.value,
                        }))
                      }
                      className="w-full mt-2 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm"
                      placeholder="必填：说明修改原因"
                    />
                  )}
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      {!reviewQuestions.length && (
        <Card padding="lg" className="text-center">
          <ExclamationTriangleIcon className="w-10 h-10 mx-auto text-warning mb-2" />
          <p>当前任务没有可复核的提交答案</p>
        </Card>
      )}

      <Card padding="lg" className="mt-5">
        <label className="font-medium">护士补充问诊摘要</label>
        <textarea
          value={supplementaryInquiry}
          onChange={(event) => setSupplementaryInquiry(event.target.value)}
          rows={4}
          className="w-full mt-2 rounded-xl border border-border p-3"
          placeholder="记录护士补问内容、患者补充说明和临床判断依据"
        />
      </Card>

      {error && (
        <div className="mt-4 rounded-xl bg-red-50 border border-red-200 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="mt-5 flex flex-col sm:flex-row justify-end gap-3">
        <Button
          variant="outline"
          disabled={submitting}
          onClick={() => void persistReview('draft')}
        >
          保存草稿
        </Button>
        <Button
          variant="danger"
          disabled={submitting}
          onClick={() => void persistReview('returned')}
        >
          退回患者重评
        </Button>
        <Button
          loading={submitting}
          onClick={() => void persistReview('confirmed')}
          disabled={!reviewQuestions.length}
        >
          <CheckCircleIcon className="w-5 h-5 mr-2" />
          确认最终结果
        </Button>
      </div>
    </NurseLayout>
  );
}
