'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import PatientLayout from '@/components/layout/PatientLayout';
import { Card } from '@/components/shared/Card';
import { Button } from '@/components/shared/Button';
import { Input } from '@/components/shared/Input';
import { mockTasks } from '@/lib/mock/data';
import {
  ChatBubbleLeftRightIcon,
  DocumentTextIcon,
  ClockIcon,
} from '@heroicons/react/24/outline';

export default function PatientPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [taskNo, setTaskNo] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    // 从 URL 读取任务编号
    const taskNoParam = searchParams.get('taskNo');
    if (taskNoParam) {
      setTaskNo(taskNoParam);
    }
  }, [searchParams]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    // 模拟验证延迟
    await new Promise((resolve) => setTimeout(resolve, 800));

    // 查找任务
    const task = mockTasks.find((t) => t.taskNo === taskNo);

    if (!task) {
      setError('任务不存在，请检查任务编号');
      setLoading(false);
      return;
    }

    // 根据采集方式跳转
    if (task.collectionMode === 'ai_dialogue') {
      router.push(`/patient/dialogue/${task.id}`);
    } else {
      router.push(`/patient/form/${task.id}`);
    }
  };

  return (
    <PatientLayout>
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <div className="w-full max-w-md">
          {/* Logo 和标题 */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-primary rounded-2xl mb-4">
              <span className="text-3xl text-white font-bold">医</span>
            </div>
            <h1 className="text-2xl font-serif font-medium text-foreground mb-2">
              患者<span className="text-primary italic">入院评估</span>
            </h1>
            <p className="text-sm text-foreground-muted">请输入护士提供的任务编号</p>
          </div>

          {/* 输入表单 */}
          <Card padding="lg" className="mb-6">
            <form onSubmit={handleSubmit} className="space-y-4">
              <Input
                label="任务编号"
                value={taskNo}
                onChange={(e) => {
                  setTaskNo(e.target.value);
                  setError('');
                }}
                placeholder="请输入任务编号"
                error={error}
                required
              />
              <Button type="submit" className="w-full" loading={loading}>
                开始评估
              </Button>
            </form>

            {/* 快速测试 */}
            <div className="mt-6 pt-6 border-t border-border">
              <p className="text-xs text-foreground-muted text-center mb-3">快速测试</p>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setTaskNo(mockTasks[0]?.taskNo || '')}
                  className="p-3 rounded-xl bg-surface-secondary hover:bg-border transition-colors text-left"
                >
                  <div className="flex items-center space-x-2 mb-1">
                    <ChatBubbleLeftRightIcon className="w-4 h-4 text-primary" />
                    <span className="text-xs font-medium text-foreground">AI 对话</span>
                  </div>
                  <p className="text-xs text-foreground-muted">
                    {mockTasks[0]?.taskNo}
                  </p>
                </button>

                <button
                  type="button"
                  onClick={() => setTaskNo(mockTasks[1]?.taskNo || '')}
                  className="p-3 rounded-xl bg-surface-secondary hover:bg-border transition-colors text-left"
                >
                  <div className="flex items-center space-x-2 mb-1">
                    <DocumentTextIcon className="w-4 h-4 text-info" />
                    <span className="text-xs font-medium text-foreground">传统表单</span>
                  </div>
                  <p className="text-xs text-foreground-muted">
                    {mockTasks[1]?.taskNo}
                  </p>
                </button>
              </div>
            </div>
          </Card>

          {/* 评估方式说明 */}
          <Card padding="md">
            <div className="space-y-3">
              <div className="flex items-start space-x-3">
                <div className="p-2 bg-primary-tint rounded-lg flex-shrink-0">
                  <ChatBubbleLeftRightIcon className="w-5 h-5 text-primary" />
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-medium text-foreground mb-1">AI 智能对话</h3>
                  <p className="text-xs text-foreground-muted leading-relaxed">
                    通过语音或文字与 AI 助手对话，轻松完成评估
                  </p>
                </div>
              </div>

              <div className="flex items-start space-x-3">
                <div className="p-2 bg-blue-50 rounded-lg flex-shrink-0">
                  <DocumentTextIcon className="w-5 h-5 text-info" />
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-medium text-foreground mb-1">传统表单</h3>
                  <p className="text-xs text-foreground-muted leading-relaxed">
                    填写传统量表问卷，适合熟悉纸质表单的患者
                  </p>
                </div>
              </div>

              <div className="flex items-start space-x-3">
                <div className="p-2 bg-surface-secondary rounded-lg flex-shrink-0">
                  <ClockIcon className="w-5 h-5 text-foreground-muted" />
                </div>
                <div className="flex-1">
                  <h3 className="text-sm font-medium text-foreground mb-1">评估时长</h3>
                  <p className="text-xs text-foreground-muted leading-relaxed">
                    预计 10-15 分钟，可随时保存进度
                  </p>
                </div>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </PatientLayout>
  );
}
