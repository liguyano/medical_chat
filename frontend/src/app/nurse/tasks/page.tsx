'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import NurseLayout from '@/components/layout/NurseLayout';
import { Card } from '@/components/shared/Card';
import { Button } from '@/components/shared/Button';
import TaskCard from '@/components/task/TaskCard';
import { useUserStore } from '@/lib/stores/useUserStore';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import { mockTasks } from '@/lib/mock/data';
import type { CareTask } from '@/lib/types';
import { PlusIcon, FunnelIcon } from '@heroicons/react/24/outline';

type FilterStatus = 'all' | CareTask['taskStatus'];

export default function NurseTasksPage() {
  const router = useRouter();
  const { isAuthenticated } = useUserStore();
  const { tasks, setTasks } = useTaskStore();
  const [filterStatus, setFilterStatus] = useState<FilterStatus>('all');

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/nurse/login');
      return;
    }
    setTasks(mockTasks);
  }, [isAuthenticated, router, setTasks]);

  if (!isAuthenticated) {
    return null;
  }

  // 过滤任务
  const filteredTasks =
    filterStatus === 'all' ? tasks : tasks.filter((t) => t.taskStatus === filterStatus);

  const filterOptions: { value: FilterStatus; label: string; count: number }[] = [
    { value: 'all', label: '全部', count: tasks.length },
    {
      value: 'pending',
      label: '待开始',
      count: tasks.filter((t) => t.taskStatus === 'pending').length,
    },
    {
      value: 'in_progress',
      label: '进行中',
      count: tasks.filter((t) => t.taskStatus === 'in_progress').length,
    },
    {
      value: 'pending_review',
      label: '待审核',
      count: tasks.filter((t) => t.taskStatus === 'pending_review').length,
    },
    {
      value: 'completed',
      label: '已完成',
      count: tasks.filter((t) => t.taskStatus === 'completed').length,
    },
  ];

  return (
    <NurseLayout>
      {/* 页面头部 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-serif font-medium text-foreground mb-2">
            任务<span className="text-primary italic">管理</span>
          </h1>
          <p className="text-foreground-muted">管理所有护理评估任务</p>
        </div>
        <Button
          onClick={() => router.push('/nurse/tasks/create')}
          className="flex items-center space-x-2"
        >
          <PlusIcon className="w-5 h-5" />
          <span>创建任务</span>
        </Button>
      </div>

      {/* 过滤器 */}
      <Card padding="md" className="mb-6">
        <div className="flex items-center space-x-2 mb-4">
          <FunnelIcon className="w-5 h-5 text-foreground-muted" />
          <span className="text-sm font-medium text-foreground-muted">筛选</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {filterOptions.map((option) => (
            <button
              key={option.value}
              onClick={() => setFilterStatus(option.value)}
              className={`px-4 py-2 rounded-full text-sm font-medium transition-all duration-200 ${
                filterStatus === option.value
                  ? 'bg-primary text-white shadow-sm'
                  : 'bg-surface-secondary text-foreground-muted hover:bg-border'
              }`}
            >
              {option.label}
              <span className="ml-2 opacity-75">({option.count})</span>
            </button>
          ))}
        </div>
      </Card>

      {/* 任务列表 */}
      {filteredTasks.length === 0 ? (
        <Card padding="lg">
          <div className="text-center py-12">
            <FunnelIcon className="w-16 h-16 text-foreground-muted mx-auto mb-4 opacity-50" />
            <p className="text-foreground-muted">没有符合条件的任务</p>
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredTasks.map((task) => (
            <TaskCard key={task.id} task={task} href={`/nurse/tasks/${task.id}`} />
          ))}
        </div>
      )}
    </NurseLayout>
  );
}
