'use client';

import Link from 'next/link';
import NurseLayout from '@/components/layout/NurseLayout';
import { Card } from '@/components/shared/Card';
import { Badge } from '@/components/shared/Badge';
import { Progress } from '@/components/shared/Progress';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import {
  ChatBubbleLeftRightIcon,
  ExclamationTriangleIcon,
  SignalIcon,
} from '@heroicons/react/24/outline';

export default function NurseMonitorPage() {
  const allTasks = useTaskStore((state) => state.tasks);
  const tasks = allTasks.filter((task) =>
    ['in_progress', 'pending_review', 'completed'].includes(task.taskStatus)
  );

  return (
    <NurseLayout>
      <div className="mb-6">
        <Badge variant="info">实时状态</Badge>
        <h1 className="text-3xl mt-2">评估<span className="text-primary italic">监控中心</span></h1>
        <p className="text-foreground-muted mt-1">同步查看患者进度、AI会话、风险和人工介入请求</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <Card padding="md">
          <p className="text-sm text-foreground-muted">正在评估</p>
          <p className="text-3xl mt-1">{tasks.filter((task) => task.taskStatus === 'in_progress').length}</p>
        </Card>
        <Card padding="md">
          <p className="text-sm text-foreground-muted">等待复核</p>
          <p className="text-3xl mt-1">{tasks.filter((task) => task.taskStatus === 'pending_review').length}</p>
        </Card>
        <Card padding="md" className="border-red-200">
          <p className="text-sm text-foreground-muted">需人工介入</p>
          <p className="text-3xl mt-1 text-danger">{tasks.filter((task) => task.handoffRequired).length}</p>
        </Card>
      </div>

      <div className="space-y-4">
        {tasks.map((task) => {
          const progress = task.progress ?? { current: 0, total: 12 };
          return (
            <Link key={task.id} href={`/nurse/monitor/${task.id}`}>
              <Card hover padding="lg" className="mb-4">
                <div className="flex flex-col md:flex-row md:items-center gap-4">
                  <div className="w-12 h-12 rounded-2xl bg-primary-tint flex items-center justify-center">
                    {task.collectionMode === 'ai_dialogue' ? (
                      <ChatBubbleLeftRightIcon className="w-6 h-6 text-primary" />
                    ) : (
                      <SignalIcon className="w-6 h-6 text-info" />
                    )}
                  </div>
                  <div className="flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h2 className="font-semibold">{task.patientName} · {task.bedNo}</h2>
                      <Badge variant={task.taskStatus === 'pending_review' ? 'warning' : task.taskStatus === 'completed' ? 'success' : 'info'} size="sm">
                        {task.taskStatus === 'pending_review' ? '待复核' : task.taskStatus === 'completed' ? '已完成' : '进行中'}
                      </Badge>
                      {task.handoffRequired && <Badge variant="danger" size="sm">需人工介入</Badge>}
                    </div>
                    <p className="text-sm text-foreground-muted mt-1">
                      {task.collectionMode === 'ai_dialogue' ? 'AI对话' : '传统问卷'} · 当前阶段 {task.currentStage ?? '采集中'}
                    </p>
                    {task.handoffRequired && (
                      <p className="mt-2 text-sm text-red-700 flex items-center gap-1">
                        <ExclamationTriangleIcon className="w-4 h-4" />
                        {task.handoffReason}
                      </p>
                    )}
                  </div>
                  <div className="w-full md:w-64">
                    <Progress value={progress.current} max={progress.total} size="sm" />
                    <p className="text-xs text-right text-foreground-muted mt-1">
                      {progress.current}/{progress.total}
                    </p>
                  </div>
                </div>
              </Card>
            </Link>
          );
        })}
      </div>
    </NurseLayout>
  );
}
