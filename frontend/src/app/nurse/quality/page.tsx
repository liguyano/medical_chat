'use client';

import Link from 'next/link';
import NurseLayout from '@/components/layout/NurseLayout';
import { Card } from '@/components/shared/Card';
import { Badge } from '@/components/shared/Badge';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import { StarIcon } from '@heroicons/react/24/outline';

export default function NurseQualityPage() {
  const allTasks = useTaskStore((state) => state.tasks);
  const tasks = allTasks.filter((task) => task.collectionMode === 'ai_dialogue');
  const qualityReviews = useTaskStore((state) => state.qualityReviews);

  return (
    <NurseLayout>
      <div className="mb-6">
        <Badge variant="primary">AI质量改进</Badge>
        <h1 className="text-3xl mt-2">AI<span className="text-primary italic">质量评价</span></h1>
        <p className="text-foreground-muted mt-1">
          这里完成整次会话评价；逐条 AI 消息可在实时监控中选中并评分
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {tasks.map((task) => {
          const review = qualityReviews[task.id];
          return (
            <Link key={task.id} href={`/nurse/quality/${task.id}`}>
              <Card hover padding="lg">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h2 className="font-semibold">{task.patientName} · {task.bedNo}</h2>
                    <p className="text-sm text-foreground-muted mt-1">{task.taskNo}</p>
                  </div>
                  <Badge variant={review?.submittedAt ? 'success' : 'warning'} size="sm">
                    {review?.submittedAt ? '已评价' : '待评价'}
                  </Badge>
                </div>
                <div className="mt-5 flex items-center gap-2 text-primary">
                  <StarIcon className="w-5 h-5" />
                  <span className="text-sm">
                    {review?.submittedAt ? '查看或更新评价' : '开始质量评价'}
                  </span>
                </div>
              </Card>
            </Link>
          );
        })}
      </div>
    </NurseLayout>
  );
}
