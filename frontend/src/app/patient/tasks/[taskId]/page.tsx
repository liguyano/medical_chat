'use client';

import { useParams, useRouter } from 'next/navigation';
import PatientLayout from '@/components/layout/PatientLayout';
import { Card } from '@/components/shared/Card';
import { Button } from '@/components/shared/Button';
import { Badge } from '@/components/shared/Badge';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import {
  CheckCircleIcon,
  ClockIcon,
  DocumentTextIcon,
  ShieldCheckIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline';

export default function PatientTaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const router = useRouter();
  const task = useTaskStore((state) => state.tasks.find((item) => item.id === taskId));

  if (!task) {
    return (
      <PatientLayout title="任务详情" showBack>
        <div className="max-w-xl mx-auto p-4">
          <Card padding="lg" className="text-center">
            <p>任务不存在或已经失效</p>
            <Button className="mt-4" onClick={() => router.push('/patient/tasks')}>
              返回任务中心
            </Button>
          </Card>
        </div>
      </PatientLayout>
    );
  }

  const startPath =
    task.collectionMode === 'ai_dialogue'
      ? `/patient/dialogue/${task.id}`
      : `/patient/form/${task.id}`;

  return (
    <PatientLayout title="任务详情" showBack onBack={() => router.push('/patient/tasks')}>
      <div className="max-w-xl mx-auto p-4 space-y-4">
        <Card padding="lg">
          <div className="flex items-start justify-between gap-3">
            <div>
              <Badge variant="primary" size="sm">演示任务</Badge>
              <h1 className="text-2xl mt-3">{task.taskType}</h1>
              <p className="text-sm text-foreground-muted mt-1">
                {task.collectionMode === 'ai_dialogue' ? 'AI对话评估' : '传统问卷评估'}
              </p>
            </div>
            {task.collectionMode === 'ai_dialogue' ? (
              <SparklesIcon className="w-10 h-10 text-primary" />
            ) : (
              <DocumentTextIcon className="w-10 h-10 text-info" />
            )}
          </div>
          <div className="mt-5 grid grid-cols-2 gap-3 text-sm">
            <div className="rounded-xl bg-surface-secondary p-3">
              <ClockIcon className="w-5 h-5 text-primary mb-1" />
              预计10—15分钟
            </div>
            <div className="rounded-xl bg-surface-secondary p-3">
              <ShieldCheckIcon className="w-5 h-5 text-primary mb-1" />
              护士最终复核
            </div>
          </div>
        </Card>

        <Card padding="lg">
          <h2 className="text-xl mb-3">任务内容</h2>
          <div className="space-y-3">
            {task.scaleNames?.map((name, index) => (
              <div key={name} className="flex items-center gap-3">
                <span className="w-7 h-7 rounded-full bg-primary-tint text-primary flex items-center justify-center text-xs font-semibold">
                  {index + 1}
                </span>
                <span className="text-sm">{name}</span>
              </div>
            ))}
            {task.consentRequired && (
              <div className="flex items-center gap-3">
                <span className="w-7 h-7 rounded-full bg-amber-50 text-amber-700 flex items-center justify-center text-xs font-semibold">
                  知
                </span>
                <span className="text-sm">入院须知关键条款与签名</span>
              </div>
            )}
          </div>
        </Card>

        <Card padding="lg">
          <h2 className="text-xl mb-3">开始前说明</h2>
          <ul className="space-y-2 text-sm text-foreground-muted">
            <li>• 当前参与人：{task.participantName ?? task.patientName}</li>
            <li>• AI是护理评估助手，不能替代医生诊断。</li>
            <li>• 您可以暂停、纠正回答或随时联系护士。</li>
            <li>• 所有结果提交后均由护士确认。</li>
          </ul>
        </Card>

        {task.taskStatus === 'pending_review' ? (
          <div className="rounded-2xl bg-primary-tint border border-primary/20 p-5 text-center">
            <CheckCircleIcon className="w-9 h-9 text-primary mx-auto mb-2" />
            <p className="font-medium">评估已提交，等待护士复核</p>
          </div>
        ) : task.taskStatus === 'completed' ? (
          <Button className="w-full" onClick={() => router.push(`/patient/complete/${task.id}`)}>
            查看完成结果
          </Button>
        ) : (
          <Button className="w-full" size="lg" onClick={() => router.push(startPath)}>
            {task.taskStatus === 'in_progress' ? '从上次位置继续' : '开始评估'}
          </Button>
        )}
      </div>
    </PatientLayout>
  );
}
