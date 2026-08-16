'use client';

import NurseLayout from '@/components/layout/NurseLayout';
import { Card } from '@/components/shared/Card';
import { Badge } from '@/components/shared/Badge';
import { Button } from '@/components/shared/Button';
import { mockScales } from '@/lib/mock/data';
import { useChatStore } from '@/lib/stores/useChatStore';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import {
  ArrowPathIcon,
  BookOpenIcon,
  DocumentCheckIcon,
} from '@heroicons/react/24/outline';

export default function NurseConfigPage() {
  const resetTasks = useTaskStore((state) => state.resetDemoData);
  const resetChat = useChatStore((state) => state.resetDemoData);

  const reset = () => {
    resetTasks();
    resetChat();
  };

  return (
    <NurseLayout>
      <div className="mb-6">
        <Badge variant="primary">原型配置中心</Badge>
        <h1 className="text-3xl mt-2">系统<span className="text-primary italic">配置</span></h1>
        <p className="text-foreground-muted mt-1">展示已注册量表、宣教材料和知情同意版本；正式系统需审批后发布</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <Card padding="lg" className="lg:col-span-2">
          <div className="flex items-center gap-2 mb-4">
            <DocumentCheckIcon className="w-6 h-6 text-primary" />
            <h2 className="text-xl">已注册评估量表</h2>
          </div>
          <div className="space-y-3">
            {mockScales.map((scale) => (
              <div key={scale.id} className="rounded-xl bg-surface-secondary p-4 flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium">{scale.scaleName}</p>
                  <p className="text-sm text-foreground-muted mt-1">{scale.description}</p>
                </div>
                <Badge variant="success" size="sm">v1.0 已发布</Badge>
              </div>
            ))}
          </div>
        </Card>

        <div className="space-y-5">
          <Card padding="lg">
            <BookOpenIcon className="w-6 h-6 text-primary mb-3" />
            <h2 className="text-xl">宣教材料</h2>
            <p className="text-sm text-foreground-muted mt-2">4项已发布：过敏、防跌倒、禁烟、用药安全。</p>
          </Card>
          <Card padding="lg">
            <DocumentCheckIcon className="w-6 h-6 text-primary mb-3" />
            <h2 className="text-xl">知情同意书</h2>
            <p className="text-sm text-foreground-muted mt-2">入院须知 v1.0，包含3条强制确认条款。</p>
          </Card>
          <Card padding="lg" className="border-amber-200">
            <ArrowPathIcon className="w-6 h-6 text-warning mb-3" />
            <h2 className="text-xl">演示数据重置</h2>
            <p className="text-sm text-foreground-muted mt-2 mb-4">清除本地操作结果并恢复初始任务、对话和风险事件。</p>
            <Button variant="outline" className="w-full" onClick={reset}>恢复初始演示数据</Button>
          </Card>
        </div>
      </div>
    </NurseLayout>
  );
}
