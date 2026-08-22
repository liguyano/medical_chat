'use client';

import Link from 'next/link';
import { Card } from '@/components/shared/Card';
import { Badge } from '@/components/shared/Badge';
import { Progress } from '@/components/shared/Progress';
import type { CareTask } from '@/lib/types';
import { formatDateTime } from '@/lib/utils';
import {
  ClockIcon,
  UserIcon,
  ChatBubbleLeftRightIcon,
  DocumentTextIcon,
} from '@heroicons/react/24/outline';

interface TaskCardProps {
  task: CareTask;
  href: string;
}

const statusConfig = {
  pending: { label: '待开始', variant: 'default' as const },
  in_progress: { label: '进行中', variant: 'info' as const },
  pending_review: { label: '待审核', variant: 'warning' as const },
  completed: { label: '已完成', variant: 'success' as const },
  cancelled: { label: '已取消', variant: 'default' as const },
};

const modeConfig = {
  ai_dialogue: {
    label: 'AI 对话',
    icon: ChatBubbleLeftRightIcon,
    color: 'text-primary',
  },
  traditional_form: {
    label: '传统表单',
    icon: DocumentTextIcon,
    color: 'text-info',
  },
};

export default function TaskCard({ task, href }: TaskCardProps) {
  const preparationFailed = task.preparation?.status === 'failed';
  const preparationRunning =
    task.preparation?.status === 'queued' ||
    task.preparation?.status === 'running';
  const statusInfo = preparationFailed
    ? { label: '创建失败', variant: 'danger' as const }
    : preparationRunning
      ? { label: '准备中', variant: 'warning' as const }
      : statusConfig[task.taskStatus];
  const modeInfo = modeConfig[task.collectionMode];
  const ModeIcon = modeInfo.icon;

  return (
    <Link href={href}>
      <Card hover padding="md" className="cursor-pointer">
        {/* 头部信息 */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex-1">
            <div className="flex items-center space-x-2 mb-1">
              <h3 className="text-lg font-medium text-foreground">{task.patientName}</h3>
              <Badge variant={statusInfo.variant} size="sm">
                {statusInfo.label}
              </Badge>
              {task.handoffRequired && (
                <Badge variant="danger" size="sm">需人工介入</Badge>
              )}
            </div>
            <div className="flex items-center space-x-4 text-sm text-foreground-muted">
              <span>{task.bedNo}</span>
              <span>•</span>
              <span>{task.taskType}</span>
            </div>
          </div>
          <div className={`p-2 rounded-xl bg-surface-secondary ${modeInfo.color}`}>
            <ModeIcon className="w-5 h-5" />
          </div>
        </div>

        {/* 进度条（如果有） */}
        {task.progress && (
          <div className="mb-4">
            <Progress
              value={task.progress.current}
              max={task.progress.total}
              variant="primary"
              size="sm"
              showLabel
            />
          </div>
        )}

        {/* 底部信息 */}
        <div className="flex items-center justify-between text-xs text-foreground-muted pt-3 border-t border-border">
          <div className="flex items-center space-x-1">
            <UserIcon className="w-4 h-4" />
            <span>{task.assignedNurseName}</span>
          </div>
          <div className="flex items-center space-x-1">
            <ClockIcon className="w-4 h-4" />
            <span>{formatDateTime(task.createdAt)}</span>
          </div>
        </div>
      </Card>
    </Link>
  );
}
