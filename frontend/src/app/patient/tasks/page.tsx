'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import PatientLayout from '@/components/layout/PatientLayout';
import { Card } from '@/components/shared/Card';
import { Badge } from '@/components/shared/Badge';
import { Progress } from '@/components/shared/Progress';
import { careRepository } from '@/lib/repositories';
import { isRequestCancelled, abortRequest } from '@/lib/api/httpClient';
import { runtimeConfig } from '@/lib/runtime/config';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import { useUserStore } from '@/lib/stores/useUserStore';
import {
  ChatBubbleLeftRightIcon,
  CheckCircleIcon,
  ClipboardDocumentListIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';

const statusLabels = {
  pending: { label: '待完成', variant: 'warning' as const },
  in_progress: { label: '进行中', variant: 'info' as const },
  pending_review: { label: '等待护士复核', variant: 'primary' as const },
  completed: { label: '已完成', variant: 'success' as const },
  cancelled: { label: '已取消', variant: 'default' as const },
};

export default function PatientTasksPage() {
  const router = useRouter();
  const { user } = useUserStore();
  const allTasks = useTaskStore((state) => state.tasks);
  const setTasks = useTaskStore((state) => state.setTasks);
  const [loadError, setLoadError] = useState('');
  const tasks = allTasks.filter((task) => task.patientId === user?.id);

  useEffect(() => {
    if (runtimeConfig.dataMode !== 'api') return;
    if (!user) {
      router.replace('/patient');
      return;
    }

    const controller = new AbortController();
    void careRepository
      .listMyTasks(controller.signal)
      .then((nextTasks) => {
        setTasks(nextTasks);
        setLoadError('');
      })
      .catch((error) => {
        if (controller.signal.aborted || isRequestCancelled(error)) return;
        setLoadError(
          error instanceof Error ? error.message : '任务加载失败'
        );
      });
    return () => abortRequest(controller);
  }, [router, setTasks, user]);

  return (
    <PatientLayout title="我的护理任务" showNavigation>
      <div className="max-w-xl mx-auto p-4">
        <div className="mb-5">
          <h1 className="text-2xl mb-1">任务中心</h1>
          <p className="text-sm text-foreground-muted">
            {runtimeConfig.dataMode === 'api'
              ? '请选择医护端发布的任务，完成 AI 文本问诊后等待护士复核。'
              : '请按顺序完成评估、宣教与知情同意，提交后由护士复核。'}
          </p>
        </div>

        {loadError && (
          <div className="mb-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {loadError}
          </div>
        )}

        {tasks.length === 0 ? (
          <Card padding="lg" className="text-center">
            <ClipboardDocumentListIcon className="w-14 h-14 mx-auto text-foreground-muted opacity-40 mb-3" />
            <p className="font-medium">当前没有护理任务</p>
            <p className="text-sm text-foreground-muted mt-1">如有疑问，请联系责任护士。</p>
          </Card>
        ) : (
          <div className="space-y-4">
            {tasks.map((task) => {
              const status = statusLabels[task.taskStatus];
              const current = task.progress?.current ?? 0;
              const total = task.progress?.total ?? 15;
              return (
                <Link key={task.id} href={`/patient/tasks/${task.id}`}>
                  <Card hover padding="lg" className="mb-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2 mb-1">
                          {task.collectionMode === 'ai_dialogue' ? (
                            <ChatBubbleLeftRightIcon className="w-5 h-5 text-primary" />
                          ) : (
                            <ClipboardDocumentListIcon className="w-5 h-5 text-info" />
                          )}
                          <h2 className="text-lg font-sans font-semibold">{task.taskType}</h2>
                        </div>
                        <p className="text-sm text-foreground-muted">
                          {task.scaleNames?.length ?? 1}项量表 · {task.collectionMode === 'ai_dialogue' ? 'AI对话' : '传统问卷'}
                        </p>
                      </div>
                      <Badge variant={status.variant} size="sm">{status.label}</Badge>
                    </div>

                    {task.handoffRequired && (
                      <div className="mt-4 flex items-start gap-2 rounded-xl bg-amber-50 border border-amber-200 p-3 text-sm text-amber-800">
                        <ExclamationTriangleIcon className="w-5 h-5 flex-shrink-0" />
                        <span>护士正在处理：{task.handoffReason}</span>
                      </div>
                    )}

                    <div className="mt-4">
                      <Progress value={current} max={total} size="sm" />
                      <div className="flex items-center justify-between mt-2 text-xs text-foreground-muted">
                        <span>{current} / {total}</span>
                        <span>{task.assignedNurseName}</span>
                      </div>
                    </div>

                    {task.taskStatus === 'completed' && (
                      <div className="mt-3 flex items-center gap-2 text-sm text-green-700">
                        <CheckCircleIcon className="w-4 h-4" />
                        已由护士确认
                      </div>
                    )}
                  </Card>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </PatientLayout>
  );
}
