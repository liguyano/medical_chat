'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import NurseLayout from '@/components/layout/NurseLayout';
import { Card } from '@/components/shared/Card';
import { Badge } from '@/components/shared/Badge';
import { Button } from '@/components/shared/Button';
import { IntegrationStatus } from '@/components/shared/IntegrationStatus';
import { abortRequest, isRequestCancelled } from '@/lib/api/httpClient';
import { careRepository } from '@/lib/repositories';
import { runtimeConfig } from '@/lib/runtime/config';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import { useUserStore } from '@/lib/stores/useUserStore';
import { cn } from '@/lib/utils';
import {
  ArrowLeftIcon,
  CheckCircleIcon,
  StarIcon,
} from '@heroicons/react/24/outline';

const dialogueDimensions = ['CICARE规范性', '信息准确性', '问询完整性', '追问合理性', '宣教适宜性', '沟通友好度', '安全性'];
const assessmentDimensions = ['答案抽取准确性', '答案完整性', '临床计分正确性', '风险识别正确性', '护理建议匹配度'];
const defaultDialogueScores = Object.fromEntries(
  dialogueDimensions.map((item) => [item, 4])
);
const defaultAssessmentScores = Object.fromEntries(
  assessmentDimensions.map((item) => [item, 4])
);

export default function NurseQualityDetailPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const router = useRouter();
  const task = useTaskStore((state) => state.tasks.find((item) => item.id === taskId));
  const addTask = useTaskStore((state) => state.addTask);
  const storedReview = useTaskStore((state) => state.qualityReviews[taskId]);
  const saveQualityReview = useTaskStore((state) => state.saveQualityReview);
  const clearQualityReview = useTaskStore((state) => state.clearQualityReview);
  const reviewerId = useUserStore((state) => state.user?.id ?? 'N001');
  const existing =
    runtimeConfig.dataMode === 'api'
      ? storedReview?.reviewerId === reviewerId
        ? storedReview
        : undefined
      : storedReview;
  const [dialogueScoreDraft, setDialogueScoreDraft] =
    useState<Record<string, number> | null>(null);
  const [assessmentScoreDraft, setAssessmentScoreDraft] =
    useState<Record<string, number> | null>(null);
  const [commentDraft, setCommentDraft] = useState<string | null>(null);
  const [savedOverride, setSavedOverride] = useState<boolean | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [loadingTask, setLoadingTask] = useState(
    runtimeConfig.dataMode === 'api' && !task
  );
  const [error, setError] = useState('');
  const dialogueScores = {
    ...defaultDialogueScores,
    ...(existing?.dialogueScores ?? {}),
    ...(dialogueScoreDraft ?? {}),
  };
  const assessmentScores = {
    ...defaultAssessmentScores,
    ...(existing?.assessmentScores ?? {}),
    ...(assessmentScoreDraft ?? {}),
  };
  const comment = commentDraft ?? existing?.comment ?? '';
  const saved = savedOverride ?? Boolean(existing?.submittedAt);

  useEffect(() => {
    if (runtimeConfig.dataMode !== 'api' || task) return;
    const controller = new AbortController();
    const loadTask = async () => {
      try {
        addTask(await careRepository.getTask(taskId, controller.signal));
        setError('');
      } catch (loadError) {
        if (!controller.signal.aborted && !isRequestCancelled(loadError)) {
          setError(
            loadError instanceof Error
              ? `任务加载失败：${loadError.message}`
              : '任务加载失败'
          );
        }
      } finally {
        if (!controller.signal.aborted) setLoadingTask(false);
      }
    };
    void loadTask();
    return () => abortRequest(controller);
  }, [addTask, task, taskId]);

  useEffect(() => {
    if (runtimeConfig.dataMode !== 'api') return;
    const controller = new AbortController();
    const load = async () => {
      try {
        const review = await careRepository.getQualityReview(
          taskId,
          reviewerId,
          controller.signal
        );
        if (!review) {
          clearQualityReview(taskId);
          return;
        }
        const normalizedReview = { ...review, taskId, reviewerId };
        saveQualityReview(normalizedReview);
        setError('');
      } catch (loadError) {
        if (!controller.signal.aborted && !isRequestCancelled(loadError)) {
          setError(
            loadError instanceof Error
              ? `质量评价加载失败：${loadError.message}`
              : '质量评价加载失败'
          );
        }
      }
    };
    void load();
    return () => abortRequest(controller);
  }, [
    clearQualityReview,
    reviewerId,
    saveQualityReview,
    taskId,
  ]);

  if (!task) {
    return (
      <NurseLayout>
        <Card padding="lg">
          {loadingTask ? '正在加载任务...' : error || '任务不存在'}
        </Card>
      </NurseLayout>
    );
  }
  const canReviewAssessment =
    task.taskStatus === 'pending_review' || task.taskStatus === 'completed';

  const renderDimensions = (
    dimensions: string[],
    values: Record<string, number>,
    onSelect: (dimension: string, score: number) => void
  ) => (
    <div className="space-y-4">
      {dimensions.map((dimension) => (
        <div key={dimension} className="rounded-xl bg-surface-secondary p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium">{dimension}</span>
            <Badge variant="primary">{values[dimension]}分</Badge>
          </div>
          <div className="grid grid-cols-5 gap-2">
            {[1, 2, 3, 4, 5].map((score) => (
              <button
                key={score}
                type="button"
                onClick={() => {
                  onSelect(dimension, score);
                  setSavedOverride(false);
                }}
                className={cn(
                  'h-10 rounded-xl border text-sm font-medium transition-colors',
                  values[dimension] === score
                    ? 'border-primary bg-primary text-white'
                    : 'border-border bg-surface hover:border-primary hover:text-primary'
                )}
                aria-pressed={values[dimension] === score}
                aria-label={`${dimension}评分 ${score} 分`}
              >
                {score}
              </button>
            ))}
          </div>
          <div className="flex justify-between text-xs text-foreground-muted mt-1">
            <span>需改进</span><span>优秀</span>
          </div>
        </div>
      ))}
    </div>
  );

  const submit = async () => {
    const review = {
      taskId,
      reviewerId,
      dialogueScores,
      assessmentScores: canReviewAssessment ? assessmentScores : {},
      comment,
      submittedAt: new Date().toISOString(),
    };
    setSubmitting(true);
    try {
      await careRepository.submitQualityReview(review);
      saveQualityReview(review);
      setDialogueScoreDraft(null);
      setAssessmentScoreDraft(null);
      setCommentDraft(null);
      setSavedOverride(null);
      setError('');
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : '质量评价提交失败'
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <NurseLayout>
      <Link href="/nurse/quality" className="inline-flex items-center gap-2 text-sm text-foreground-muted mb-3">
        <ArrowLeftIcon className="w-4 h-4" />
        返回质量评价
      </Link>
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-3 mb-6">
        <div>
          <h1 className="text-3xl">AI质量评价</h1>
          <p className="text-foreground-muted">{task.patientName} · {task.taskNo}</p>
        </div>
        <div className="flex items-center gap-2">
          <IntegrationStatus compact />
          {saved && <Badge variant="success">评价已保存</Badge>}
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <Card padding="lg">
          <div className="flex items-center gap-2 mb-4">
            <StarIcon className="w-6 h-6 text-primary" />
            <h2 className="text-xl">AI对话质量</h2>
          </div>
          {renderDimensions(
            dialogueDimensions,
            dialogueScores,
            (dimension, score) =>
              setDialogueScoreDraft({
                ...dialogueScores,
                [dimension]: score,
              })
          )}
        </Card>
        <Card padding="lg">
          <div className="flex items-center gap-2 mb-4">
            <CheckCircleIcon className="w-6 h-6 text-primary" />
            <h2 className="text-xl">AI评估质量</h2>
          </div>
          {canReviewAssessment ? (
            renderDimensions(
              assessmentDimensions,
              assessmentScores,
              (dimension, score) =>
                setAssessmentScoreDraft({
                  ...assessmentScores,
                  [dimension]: score,
                })
            )
          ) : (
            <div className="rounded-xl bg-surface-secondary p-5">
              <Badge variant="warning" size="sm">等待评估结果</Badge>
              <p className="text-sm text-foreground-muted mt-3 leading-6">
                当前任务仍在采集中。AI 结构化评估结果生成后，才可评价答案抽取、
                临床计分、风险识别和护理建议。
              </p>
            </div>
          )}
        </Card>
      </div>

      <Card padding="lg" className="mt-5">
        <label className="font-medium">总体意见</label>
        <textarea
          value={comment}
          onChange={(event) => {
            setCommentDraft(event.target.value);
            setSavedOverride(false);
          }}
          rows={4}
          className="w-full mt-2 rounded-xl border border-border p-3"
          placeholder="记录本次AI表现、典型问题和改进建议"
        />
      </Card>

      {error && (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          {error}
        </div>
      )}

      <div className="mt-5 flex justify-end gap-3">
        <Button variant="outline" onClick={() => router.push(`/nurse/monitor/${taskId}`)}>
          回到对话逐条质评
        </Button>
        <Button loading={submitting} onClick={() => void submit()}>
          提交质量评价
        </Button>
      </div>
    </NurseLayout>
  );
}
