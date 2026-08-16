'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import NurseLayout from '@/components/layout/NurseLayout';
import { Card } from '@/components/shared/Card';
import { Badge } from '@/components/shared/Badge';
import { Button } from '@/components/shared/Button';
import { IntegrationStatus } from '@/components/shared/IntegrationStatus';
import { careRepository } from '@/lib/repositories';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import {
  ArrowLeftIcon,
  CheckCircleIcon,
  StarIcon,
} from '@heroicons/react/24/outline';

const dialogueDimensions = ['CICARE规范性', '信息准确性', '问询完整性', '追问合理性', '宣教适宜性', '沟通友好度', '安全性'];
const assessmentDimensions = ['答案抽取准确性', '答案完整性', '临床计分正确性', '风险识别正确性', '护理建议匹配度'];

export default function NurseQualityDetailPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const router = useRouter();
  const task = useTaskStore((state) => state.tasks.find((item) => item.id === taskId));
  const existing = useTaskStore((state) => state.qualityReviews[taskId]);
  const saveQualityReview = useTaskStore((state) => state.saveQualityReview);
  const [dialogueScores, setDialogueScores] = useState<Record<string, number>>(
    existing?.dialogueScores ?? Object.fromEntries(dialogueDimensions.map((item) => [item, 4]))
  );
  const [assessmentScores, setAssessmentScores] = useState<Record<string, number>>(
    existing?.assessmentScores ?? Object.fromEntries(assessmentDimensions.map((item) => [item, 4]))
  );
  const [comment, setComment] = useState(existing?.comment ?? '');
  const [saved, setSaved] = useState(Boolean(existing?.submittedAt));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  if (!task) return <NurseLayout><Card padding="lg">任务不存在</Card></NurseLayout>;

  const renderDimensions = (
    dimensions: string[],
    values: Record<string, number>,
    setValues: React.Dispatch<React.SetStateAction<Record<string, number>>>
  ) => (
    <div className="space-y-4">
      {dimensions.map((dimension) => (
        <div key={dimension} className="rounded-xl bg-surface-secondary p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium">{dimension}</span>
            <Badge variant="primary">{values[dimension]}分</Badge>
          </div>
          <input
            type="range"
            min={1}
            max={5}
            value={values[dimension]}
            onChange={(event) =>
              setValues((current) => ({ ...current, [dimension]: Number(event.target.value) }))
            }
            className="w-full accent-primary"
          />
          <div className="flex justify-between text-xs text-foreground-muted">
            <span>需改进</span><span>优秀</span>
          </div>
        </div>
      ))}
    </div>
  );

  const submit = async () => {
    const review = {
      taskId,
      dialogueScores,
      assessmentScores,
      comment,
      submittedAt: new Date().toISOString(),
    };
    setSubmitting(true);
    try {
      await careRepository.submitQualityReview(review);
      saveQualityReview(review);
      setSaved(true);
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
          {renderDimensions(dialogueDimensions, dialogueScores, setDialogueScores)}
        </Card>
        <Card padding="lg">
          <div className="flex items-center gap-2 mb-4">
            <CheckCircleIcon className="w-6 h-6 text-primary" />
            <h2 className="text-xl">AI评估质量</h2>
          </div>
          {renderDimensions(assessmentDimensions, assessmentScores, setAssessmentScores)}
        </Card>
      </div>

      <Card padding="lg" className="mt-5">
        <label className="font-medium">总体意见</label>
        <textarea
          value={comment}
          onChange={(event) => setComment(event.target.value)}
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
          查看对话证据
        </Button>
        <Button loading={submitting} onClick={() => void submit()}>
          提交质量评价
        </Button>
      </div>
    </NurseLayout>
  );
}
