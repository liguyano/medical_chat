'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import PatientLayout from '@/components/layout/PatientLayout';
import { PatientIcon } from '@/components/patient/PatientIcon';
import { PatientState } from '@/components/patient/PatientState';
import { abortRequest, isRequestCancelled } from '@/lib/api/httpClient';
import { groupPatientTasks } from '@/lib/patient/taskGroups';
import { careRepository } from '@/lib/repositories';
import { runtimeConfig } from '@/lib/runtime/config';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import { useUserStore } from '@/lib/stores/useUserStore';
import type { CareTask } from '@/lib/types';

const statusLabels: Record<CareTask['taskStatus'], string> = {
  pending: '待完成',
  in_progress: '进行中',
  pending_review: '等待护士复核',
  completed: '已完成',
  cancelled: '已取消',
};

export default function PatientTasksPage() {
  const router = useRouter();
  const user = useUserStore((state) => state.user);
  const hasHydrated = useUserStore((state) => state.hasHydrated);
  const allTasks = useTaskStore((state) => state.tasks);
  const setTasks = useTaskStore((state) => state.setTasks);
  const [loadError, setLoadError] = useState('');
  const tasks = allTasks.filter((task) => task.patientId === user?.id);
  const taskGroups = groupPatientTasks(tasks);

  useEffect(() => {
    if (runtimeConfig.dataMode !== 'api' || !hasHydrated) return;
    if (!user) {
      router.replace('/patient');
      return;
    }

    const controller = new AbortController();
    // API 模式先清理旧浏览器快照，避免后台准备中的任务在请求完成前短暂可见。
    setTasks([]);
    const loadTasks = async () => {
      try {
        const nextTasks = await careRepository.listPatientTasks(
          controller.signal
        );
        setTasks(nextTasks);
        setLoadError('');
      } catch (error) {
        if (controller.signal.aborted || isRequestCancelled(error)) return;
        setLoadError(error instanceof Error ? error.message : '任务加载失败');
      }
    };
    void loadTasks();
    const timer = window.setInterval(() => {
      void loadTasks();
    }, 3000);
    return () => {
      window.clearInterval(timer);
      abortRequest(controller);
    };
  }, [hasHydrated, router, setTasks, user]);

  const renderActiveTask = (task: CareTask) => {
    const current = task.progress?.current ?? 0;
    const total = task.progress?.total ?? 15;
    const percentage = Math.round((current / Math.max(total, 1)) * 100);

    return (
      <article key={task.id} className="patient-card-soft p-4">
        <div className="flex items-start gap-3">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#ff795c] to-[#ff5235] text-white">
            <PatientIcon
              name={task.collectionMode === 'ai_dialogue' ? 'nav-assistant' : 'clipboard'}
              className="h-7 w-7"
            />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-[20px] font-black">{task.taskType}</h2>
              <span className="rounded-full border border-[#9bd9dc] bg-[#e8f7f8] px-2 py-0.5 text-xs font-bold text-[#24898f]">
                {task.collectionMode === 'ai_dialogue' ? 'AI 对话' : '传统问卷'}
              </span>
            </div>
            <p className="mt-1 text-sm text-foreground-muted">
              {task.scaleNames?.length ?? 1} 项量表 · 责任护士 {task.assignedNurseName}
            </p>
          </div>
          <span aria-hidden="true" className="mt-0.5 text-3xl leading-none text-[#796f68]">
            ›
          </span>
        </div>

        {task.handoffRequired && (
          <div className="mt-3 flex gap-2 rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-800">
            <PatientIcon name="nurse" className="mt-0.5 h-5 w-5" />
            <span>护士正在处理：{task.handoffReason}</span>
          </div>
        )}

        <div className="mt-4 pl-[60px]">
          <div className="flex items-end justify-between">
            <p className="text-[16px] font-bold">
              <span className="text-[25px] text-primary">{current}</span>
              <span className="mx-1 text-foreground-muted">/</span>
              {total}
            </p>
            <span className="rounded-full bg-[#ffe1d1] px-3 py-1 text-xs font-bold text-primary">
              {statusLabels[task.taskStatus]}
            </span>
          </div>
          <div className="patient-progress-track mt-2">
            <div
              className="patient-progress-value"
              style={{ width: `${percentage}%` }}
            />
          </div>
          <div className="mt-3 flex items-center justify-between gap-3">
            <p className="flex items-center gap-1.5 text-sm text-foreground-muted">
              <PatientIcon name="clock" className="h-[18px] w-[18px]" />
              预计 10–15 分钟
            </p>
            <Link
              href={`/patient/tasks/${task.id}`}
              className="patient-primary-button min-h-12 min-w-[106px] px-5"
            >
              {current > 0 ? '继续' : '开始'}
            </Link>
          </div>
        </div>
      </article>
    );
  };

  const renderCompletedTask = (task: CareTask) => (
    <Link
      key={task.id}
      href={`/patient/tasks/${task.id}`}
      className="flex min-h-16 items-center gap-3 border-b border-border px-4 last:border-b-0"
    >
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-[#4ba7a3] text-white">
        <PatientIcon name="check-circle" className="h-5 w-5" />
      </span>
      <span className="min-w-0 flex-1 truncate text-[16px] font-bold">
        {task.taskType}
      </span>
      <span className="text-sm text-[#7d8c82]">
        {task.taskStatus === 'pending_review' ? '待复核' : '已完成'}
      </span>
      <span aria-hidden="true" className="text-2xl leading-none text-[#918a85]">
        ›
      </span>
    </Link>
  );

  return (
    <PatientLayout showNavigation>
      <div className="px-[18px] pb-4 pt-7">
        <div className="relative">
          <h1 className="text-[29px] font-black text-[#3e1f18]">我的护理任务</h1>
          <span className="absolute -right-1 -top-3 flex h-16 w-16 items-center justify-center rounded-3xl bg-[#fff0df] text-[#ed8b4d]">
            <PatientIcon name="clipboard" className="h-9 w-9" />
          </span>
        </div>

        <section className="patient-card mt-8 flex items-center gap-4 px-4 py-4">
          <span className="grid h-14 w-14 shrink-0 place-items-center rounded-full bg-[#fff0df] text-[#e98345]">
            <PatientIcon name="document" className="h-7 w-7" />
          </span>
          <p className="text-lg font-black">
            本次住院
            <span className="mx-2 text-[32px] text-primary">
              {taskGroups.unfinished.length}
            </span>
            项待完成
          </p>
        </section>

        {loadError && (
          <div
            role="alert"
            className="mt-4 rounded-2xl border border-red-200 bg-red-50 p-3 text-sm text-red-700"
          >
            {loadError}
          </div>
        )}

        {tasks.length === 0 ? (
          <PatientState
            kind={loadError ? 'voice-error' : 'empty-tasks'}
            title={loadError ? '护理任务加载失败' : '当前没有护理任务'}
            description={
              loadError
                ? '请检查网络后重试；如果问题持续，请联系责任护士。'
                : '新任务会在医护端准备完成后显示。'
            }
            className="mt-5"
          />
        ) : (
          <div className="mt-5 space-y-7">
            {taskGroups.unfinished.length > 0 && (
              <section aria-labelledby="active-task-heading">
                <h2
                  id="active-task-heading"
                  className="mb-3 text-[18px] font-bold text-foreground-muted"
                >
                  进行中
                </h2>
                <div className="space-y-4">
                  {taskGroups.unfinished.map(renderActiveTask)}
                </div>
              </section>
            )}

            {taskGroups.completed.length > 0 && (
              <section aria-labelledby="completed-task-heading">
                <h2
                  id="completed-task-heading"
                  className="mb-3 text-[18px] font-bold text-foreground-muted"
                >
                  已完成
                </h2>
                <div className="patient-card overflow-hidden">
                  {taskGroups.completed.map(renderCompletedTask)}
                </div>
              </section>
            )}

            {taskGroups.cancelled.length > 0 && (
              <section aria-labelledby="cancelled-task-heading">
                <h2
                  id="cancelled-task-heading"
                  className="mb-3 text-[18px] font-bold text-foreground-muted"
                >
                  已取消
                </h2>
                <div className="patient-card overflow-hidden opacity-70">
                  {taskGroups.cancelled.map(renderCompletedTask)}
                </div>
              </section>
            )}
          </div>
        )}
      </div>
    </PatientLayout>
  );
}
