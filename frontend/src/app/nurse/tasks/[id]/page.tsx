'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import NurseLayout from '@/components/layout/NurseLayout';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/shared/Card';
import { Button } from '@/components/shared/Button';
import { Badge } from '@/components/shared/Badge';
import { Progress } from '@/components/shared/Progress';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import type { CareTask } from '@/lib/types';
import {
  ArrowLeftIcon,
  UserCircleIcon,
  CalendarIcon,
  ClipboardDocumentCheckIcon,
  ChatBubbleLeftRightIcon,
  DocumentTextIcon,
  QrCodeIcon,
  CheckCircleIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';

interface PageProps {
  params: {
    id: string;
  };
}

export default function TaskDetailPage({ params }: PageProps) {
  const router = useRouter();
  const { tasks, updateTaskStatus } = useTaskStore();
  const [task, setTask] = useState<CareTask | null>(null);
  const [loading, setLoading] = useState(false);
  const [showQRCode, setShowQRCode] = useState(false);

  useEffect(() => {
    const foundTask = tasks.find((t) => t.id === params.id);
    setTask(foundTask || null);
  }, [params.id, tasks]);

  if (!task) {
    return (
      <NurseLayout>
        <div className="flex items-center justify-center h-[60vh]">
          <div className="text-center">
            <p className="text-foreground-muted">任务不存在</p>
            <Button
              variant="outline"
              onClick={() => router.push('/nurse/tasks')}
              className="mt-4"
            >
              返回任务列表
            </Button>
          </div>
        </div>
      </NurseLayout>
    );
  }

  const getStatusInfo = (status: string) => {
    const statusMap = {
      pending: { label: '待开始', variant: 'warning' as const, color: 'bg-warning' },
      in_progress: { label: '进行中', variant: 'info' as const, color: 'bg-info' },
      pending_review: { label: '待审核', variant: 'primary' as const, color: 'bg-primary' },
      completed: { label: '已完成', variant: 'success' as const, color: 'bg-success' },
      cancelled: { label: '已取消', variant: 'default' as const, color: 'bg-foreground-muted' },
    };
    return statusMap[status as keyof typeof statusMap] || statusMap.pending;
  };

  const statusInfo = getStatusInfo(task.taskStatus);

  const handleStartTask = async () => {
    setLoading(true);
    await new Promise((resolve) => setTimeout(resolve, 800));
    updateTaskStatus(task.id, 'in_progress');
    setLoading(false);
  };

  const handleApprove = async () => {
    setLoading(true);
    await new Promise((resolve) => setTimeout(resolve, 1000));
    updateTaskStatus(task.id, 'completed');
    setLoading(false);
    router.push('/nurse/tasks');
  };

  const handleReject = async () => {
    setLoading(true);
    await new Promise((resolve) => setTimeout(resolve, 1000));
    updateTaskStatus(task.id, 'in_progress');
    setLoading(false);
  };

  const handleGenerateQRCode = () => {
    setShowQRCode(true);
  };

  const patientUrl = `${window.location.origin}/patient?taskNo=${task.taskNo}`;

  return (
    <NurseLayout>
      <div className="max-w-5xl mx-auto">
        {/* 返回按钮 */}
        <button
          onClick={() => router.back()}
          className="flex items-center space-x-2 text-foreground-muted hover:text-foreground transition-colors mb-6"
        >
          <ArrowLeftIcon className="w-5 h-5" />
          <span>返回</span>
        </button>

        {/* 页面标题 */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-3xl font-serif font-medium text-foreground mb-2">
              任务<span className="text-primary italic">详情</span>
            </h1>
            <p className="text-foreground-muted">任务编号: {task.taskNo}</p>
          </div>
          <Badge variant={statusInfo.variant} size="lg">
            {statusInfo.label}
          </Badge>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* 左侧主要信息 */}
          <div className="lg:col-span-2 space-y-6">
            {/* 患者信息 */}
            <Card padding="lg">
              <CardHeader>
                <CardTitle>患者信息</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs text-foreground-muted">患者姓名</label>
                    <p className="text-sm font-medium text-foreground mt-1">
                      {task.patientName}
                    </p>
                  </div>
                  <div>
                    <label className="text-xs text-foreground-muted">床号</label>
                    <p className="text-sm font-medium text-foreground mt-1">{task.bedNo}</p>
                  </div>
                  <div>
                    <label className="text-xs text-foreground-muted">住院号</label>
                    <p className="text-sm font-medium text-foreground mt-1">
                      {task.encounterNo}
                    </p>
                  </div>
                  <div>
                    <label className="text-xs text-foreground-muted">科室</label>
                    <p className="text-sm font-medium text-foreground mt-1">
                      {task.department}
                    </p>
                  </div>
                  <div className="col-span-2">
                    <label className="text-xs text-foreground-muted">病区</label>
                    <p className="text-sm font-medium text-foreground mt-1">
                      {task.wardName}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* 任务信息 */}
            <Card padding="lg">
              <CardHeader>
                <CardTitle>任务信息</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="flex items-start space-x-3">
                    <ClipboardDocumentCheckIcon className="w-5 h-5 text-foreground-muted flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <label className="text-xs text-foreground-muted">任务类型</label>
                      <p className="text-sm font-medium text-foreground mt-1">
                        {task.taskType}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-start space-x-3">
                    {task.collectionMode === 'ai_dialogue' ? (
                      <ChatBubbleLeftRightIcon className="w-5 h-5 text-primary flex-shrink-0 mt-0.5" />
                    ) : (
                      <DocumentTextIcon className="w-5 h-5 text-info flex-shrink-0 mt-0.5" />
                    )}
                    <div className="flex-1">
                      <label className="text-xs text-foreground-muted">采集方式</label>
                      <p className="text-sm font-medium text-foreground mt-1">
                        {task.collectionMode === 'ai_dialogue' ? 'AI 对话采集' : '传统表单'}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-start space-x-3">
                    <DocumentTextIcon className="w-5 h-5 text-foreground-muted flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <label className="text-xs text-foreground-muted">量表信息</label>
                      <p className="text-sm font-medium text-foreground mt-1">
                        {task.scaleName} ({task.scaleVersion})
                      </p>
                    </div>
                  </div>

                  <div className="flex items-start space-x-3">
                    <UserCircleIcon className="w-5 h-5 text-foreground-muted flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <label className="text-xs text-foreground-muted">责任护士</label>
                      <p className="text-sm font-medium text-foreground mt-1">
                        {task.assignedNurseName}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-start space-x-3">
                    <CalendarIcon className="w-5 h-5 text-foreground-muted flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <label className="text-xs text-foreground-muted">创建时间</label>
                      <p className="text-sm font-medium text-foreground mt-1">
                        {new Date(task.createdAt).toLocaleString('zh-CN')}
                      </p>
                    </div>
                  </div>

                  {task.completedAt && (
                    <div className="flex items-start space-x-3">
                      <CheckCircleIcon className="w-5 h-5 text-success flex-shrink-0 mt-0.5" />
                      <div className="flex-1">
                        <label className="text-xs text-foreground-muted">完成时间</label>
                        <p className="text-sm font-medium text-foreground mt-1">
                          {new Date(task.completedAt).toLocaleString('zh-CN')}
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* 评估进度（仅进行中状态显示） */}
            {task.taskStatus === 'in_progress' && (
              <Card padding="lg">
                <CardHeader>
                  <CardTitle>评估进度</CardTitle>
                </CardHeader>
                <CardContent>
                  <Progress value={45} max={100} variant="primary" size="md" showLabel />
                  <p className="text-xs text-foreground-muted mt-3">
                    患者正在填写评估问卷，已完成 45%
                  </p>
                </CardContent>
              </Card>
            )}

            {/* 审核区域（待审核状态） */}
            {task.taskStatus === 'pending_review' && (
              <Card padding="lg">
                <CardHeader>
                  <CardTitle>评估结果审核</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    <div className="p-4 bg-surface-secondary rounded-xl">
                      <h4 className="text-sm font-medium text-foreground mb-2">
                        AI 提取的结构化数据
                      </h4>
                      <div className="space-y-2 text-xs">
                        <div className="flex justify-between">
                          <span className="text-foreground-muted">年龄:</span>
                          <span className="text-foreground font-medium">65 岁</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-foreground-muted">过敏史:</span>
                          <span className="text-foreground font-medium">青霉素过敏</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-foreground-muted">既往病史:</span>
                          <span className="text-foreground font-medium">高血压、糖尿病</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-foreground-muted">主要症状:</span>
                          <span className="text-foreground font-medium">胸痛、气短</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center space-x-3">
                      <Button
                        variant="outline"
                        onClick={() => {
                          // TODO: 查看完整对话记录
                          console.log('查看完整对话');
                        }}
                        className="flex-1"
                      >
                        查看完整记录
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => {
                          // TODO: 对比量表
                          console.log('对比量表');
                        }}
                        className="flex-1"
                      >
                        对比量表
                      </Button>
                    </div>

                    <div className="border-t border-border pt-4 flex items-center space-x-3">
                      <Button
                        variant="outline"
                        onClick={handleReject}
                        loading={loading}
                        className="flex-1"
                      >
                        <XMarkIcon className="w-4 h-4 mr-1" />
                        退回修改
                      </Button>
                      <Button
                        onClick={handleApprove}
                        loading={loading}
                        className="flex-1"
                      >
                        <CheckCircleIcon className="w-4 h-4 mr-1" />
                        通过审核
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>

          {/* 右侧操作区 */}
          <div className="space-y-6">
            {/* 操作卡片 */}
            <Card padding="lg">
              <CardHeader>
                <CardTitle>操作</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {task.taskStatus === 'pending' && (
                    <>
                      <Button
                        onClick={handleStartTask}
                        loading={loading}
                        className="w-full"
                      >
                        开始任务
                      </Button>
                      <Button
                        variant="outline"
                        onClick={handleGenerateQRCode}
                        className="w-full"
                      >
                        <QrCodeIcon className="w-4 h-4 mr-2" />
                        生成二维码
                      </Button>
                    </>
                  )}

                  {task.taskStatus === 'in_progress' && (
                    <Button
                      variant="outline"
                      onClick={() => {
                        // TODO: 查看实时进度
                        console.log('查看实时进度');
                      }}
                      className="w-full"
                    >
                      查看实时进度
                    </Button>
                  )}

                  {task.taskStatus === 'completed' && (
                    <>
                      <Button
                        variant="outline"
                        onClick={() => {
                          // TODO: 查看评估报告
                          console.log('查看评估报告');
                        }}
                        className="w-full"
                      >
                        查看评估报告
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => {
                          // TODO: 生成护理计划
                          console.log('生成护理计划');
                        }}
                        className="w-full"
                      >
                        生成护理计划
                      </Button>
                    </>
                  )}

                  <Button
                    variant="ghost"
                    onClick={() => {
                      // TODO: 编辑任务
                      console.log('编辑任务');
                    }}
                    className="w-full"
                  >
                    编辑任务
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* 二维码卡片 */}
            {showQRCode && (
              <Card padding="lg">
                <CardHeader>
                  <CardTitle>患者端二维码</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-center">
                    <div className="w-48 h-48 bg-surface-secondary rounded-xl flex items-center justify-center mx-auto mb-4">
                      <QrCodeIcon className="w-32 h-32 text-foreground-muted" />
                    </div>
                    <p className="text-xs text-foreground-muted mb-2">
                      或发送任务编号给患者
                    </p>
                    <div className="flex items-center space-x-2">
                      <input
                        type="text"
                        value={task.taskNo}
                        readOnly
                        className="flex-1 px-3 py-2 text-sm rounded-lg border border-border bg-surface text-foreground text-center"
                      />
                      <Button
                        size="sm"
                        onClick={() => {
                          navigator.clipboard.writeText(task.taskNo);
                        }}
                      >
                        复制
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </NurseLayout>
  );
}
