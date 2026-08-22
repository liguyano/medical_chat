'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import NurseLayout from '@/components/layout/NurseLayout';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/shared/Card';
import { Button } from '@/components/shared/Button';
import { Badge } from '@/components/shared/Badge';
import { Progress } from '@/components/shared/Progress';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import { useChatStore } from '@/lib/stores/useChatStore';
import { getTaskById } from '@/lib/mock/data';
import { abortRequest, isRequestCancelled } from '@/lib/api/httpClient';
import { careRepository } from '@/lib/repositories';
import { runtimeConfig } from '@/lib/runtime/config';
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

export default function TaskDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { tasks, upsertTask, updateTaskStatus } = useTaskStore();
  const structuredAnswersByTask = useChatStore((state) => state.structuredAnswers);
  const interactionEventsByTask = useChatStore((state) => state.events);
  const structuredAnswers = structuredAnswersByTask[id] ?? [];
  const interactionEvents = interactionEventsByTask[id] ?? [];
  const [loading, setLoading] = useState(false);
  const [showQRCode, setShowQRCode] = useState(false);
  const [taskLoadError, setTaskLoadError] = useState('');
  const storedTask = tasks.find((item) => item.id === id);
  const task: CareTask | null =
    storedTask ??
    (runtimeConfig.dataMode === 'mock' ? getTaskById(id) : null) ??
    null;

  useEffect(() => {
    if (runtimeConfig.dataMode !== 'api') return;
    const controller = new AbortController();
    const loadTask = async () => {
      try {
        const loadedTask = await careRepository.getTask(id, controller.signal);
        upsertTask(loadedTask);
        setTaskLoadError('');
      } catch (loadError) {
        if (controller.signal.aborted || isRequestCancelled(loadError)) return;
        setTaskLoadError(
          loadError instanceof Error ? loadError.message : '任务加载失败'
        );
      }
    };
    void loadTask();
    const timer = window.setInterval(() => {
      void loadTask();
    }, 2000);
    return () => {
      window.clearInterval(timer);
      abortRequest(controller);
    };
  }, [id, upsertTask]);

  if (!task) {
    return (
      <NurseLayout>
        <div className="flex items-center justify-center h-[60vh]">
          <div className="text-center">
            <p className="text-foreground-muted">
              {taskLoadError || '正在加载任务...'}
            </p>
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

  const preparationFailed = task.preparation?.status === 'failed';
  const preparationRunning =
    task.preparation?.status === 'queued' ||
    task.preparation?.status === 'running';
  const statusInfo = preparationFailed
    ? { label: '创建失败', variant: 'danger' as const, color: 'bg-danger' }
    : preparationRunning
      ? { label: '准备中', variant: 'warning' as const, color: 'bg-warning' }
      : getStatusInfo(task.taskStatus);
  const progressCurrent = task.progress?.current ?? 0;
  const progressTotal = task.progress?.total ?? 0;
  const scaleName =
    task.scaleNames?.join('、') ?? task.scaleName ?? '未配置量表';

  const handleStartTask = async () => {
    setLoading(true);
    await new Promise((resolve) => setTimeout(resolve, 800));
    updateTaskStatus(task.id, 'in_progress');
    setLoading(false);
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

  const handleRetryPreparation = async () => {
    setLoading(true);
    setTaskLoadError('');
    try {
      const retriedTask = await careRepository.retryTaskPreparation(task.id);
      upsertTask(retriedTask);
    } catch (retryError) {
      setTaskLoadError(
        retryError instanceof Error ? retryError.message : '任务重试失败'
      );
    } finally {
      setLoading(false);
    }
  };

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
                        {scaleName}
                        {task.scaleVersion ? ` (${task.scaleVersion})` : ''}
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

            {task.collectionMode === 'ai_dialogue' && task.preparation && (
              <Card padding="lg">
                <CardHeader>
                  <CardTitle>AI 首问准备进度</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {[
                      ['schedule_prepare', 'Schedule 量表问题规划'],
                      ['dialog_preheat', 'Dialog Agent 预热'],
                      ['dialog_opening', '首问生成'],
                    ].map(([stage, label]) => {
                      const snapshot = task.preparation?.stages[stage];
                      const stageStatus = snapshot?.status ?? 'pending';
                      const statusLabel =
                        stageStatus === 'completed'
                          ? '已完成'
                          : stageStatus === 'running'
                            ? '执行中'
                            : stageStatus === 'failed'
                              ? '失败'
                              : '等待中';
                      return (
                        <div
                          key={stage}
                          className="rounded-xl border border-border p-3"
                        >
                          <div className="flex items-center justify-between gap-3">
                            <span className="font-medium">{label}</span>
                            <Badge
                              variant={
                                stageStatus === 'failed'
                                  ? 'danger'
                                  : stageStatus === 'completed'
                                    ? 'success'
                                    : stageStatus === 'running'
                                      ? 'info'
                                      : 'default'
                              }
                              size="sm"
                            >
                              {statusLabel}
                            </Badge>
                          </div>
                          {stage === 'schedule_prepare' &&
                            Array.isArray(snapshot?.output?.questions) && (
                              <div className="mt-2 max-h-48 overflow-y-auto rounded-lg bg-surface-secondary p-2 text-sm">
                                <p className="mb-1 text-foreground-muted">
                                  已规划问题：
                                  {snapshot.output.questions.length} 项
                                </p>
                                <ol className="list-decimal space-y-1 pl-5">
                                  {snapshot.output.questions.map(
                                    (question, index) => (
                                      <li key={`${stage}-${index}`}>
                                        {typeof question === 'object' &&
                                        question !== null &&
                                        'question_name' in question
                                          ? String(question.question_name)
                                          : String(question)}
                                      </li>
                                    )
                                  )}
                                </ol>
                              </div>
                            )}
                          {stage === 'dialog_opening' &&
                            typeof snapshot?.output?.content === 'string' &&
                            snapshot.output.content.length > 0 && (
                              <p className="mt-2 rounded-lg bg-surface-secondary p-3 text-sm leading-6">
                                首问：{String(snapshot.output.content)}
                              </p>
                            )}
                          {snapshot?.error && (
                            <p className="mt-2 text-sm text-red-700">
                              {snapshot.error}
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                  <div className="mt-4 flex items-center justify-between gap-3 text-sm">
                    <span className="text-foreground-muted">
                      {preparationFailed
                        ? `准备失败：${task.preparation.error ?? '未知错误'}`
                        : preparationRunning
                          ? `当前阶段：${task.preparation.stage ?? '后台准备中'}`
                          : task.preparation.status === 'ready'
                            ? '首问已生成，患者端已可见'
                            : '等待后台开始准备'}
                    </span>
                    {preparationFailed && (
                      <Button
                        size="sm"
                        onClick={handleRetryPreparation}
                        loading={loading}
                      >
                        重试准备
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* 评估进度（仅进行中状态显示） */}
            {task.taskStatus === 'in_progress' && !preparationRunning && !preparationFailed && (
              <Card padding="lg">
                <CardHeader>
                  <CardTitle>评估进度</CardTitle>
                </CardHeader>
                <CardContent>
                  <Progress
                    value={progressCurrent}
                    max={Math.max(progressTotal, 1)}
                    variant="primary"
                    size="md"
                    showLabel
                  />
                  <p className="text-xs text-foreground-muted mt-3">
                    患者正在进行 AI 问诊，已完成 {progressCurrent}/{progressTotal}
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
                      <h4 className="text-sm font-medium text-foreground mb-2">AI评估摘要</h4>
                      <p className="text-sm leading-6">
                        {task.aiSummary ?? '患者已完成采集，等待护士查看原始回答并确认最终结果。'}
                      </p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Badge variant="info" size="sm">{structuredAnswers.length}项结构化答案</Badge>
                        <Badge variant={interactionEvents.some((event) => event.priority === 'high') ? 'danger' : 'warning'} size="sm">
                          {interactionEvents.length}项风险/宣教事件
                        </Badge>
                      </div>
                    </div>

                    <div className="flex items-center space-x-3">
                      <Button
                        variant="outline"
                        onClick={() => router.push(`/nurse/monitor/${task.id}`)}
                        className="flex-1"
                      >
                        查看完整记录
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => router.push(`/nurse/tasks/${task.id}/review`)}
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
                        onClick={() => router.push(`/nurse/tasks/${task.id}/review`)}
                        className="flex-1"
                      >
                        <CheckCircleIcon className="w-4 h-4 mr-1" />
                        进入正式复核
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
                  {task.taskStatus === 'pending' &&
                    !preparationRunning &&
                    !preparationFailed && (
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

                  {preparationRunning && (
                    <Button variant="outline" disabled className="w-full">
                      后台准备中…
                    </Button>
                  )}

                  {preparationFailed && (
                    <Button
                      onClick={handleRetryPreparation}
                      loading={loading}
                      className="w-full"
                    >
                      重试 AI 首问准备
                    </Button>
                  )}

                  {task.taskStatus === 'in_progress' &&
                    !preparationRunning &&
                    !preparationFailed && (
                    <Button
                      variant="outline"
                      onClick={() => router.push(`/nurse/monitor/${task.id}`)}
                      className="w-full"
                    >
                      查看实时进度
                    </Button>
                  )}

                  {task.taskStatus === 'completed' && (
                    <>
                      <Button
                        onClick={() => router.push(`/nurse/tasks/${task.id}/nursing-plan`)}
                        className="w-full"
                      >
                        查看患者画像与护理计划
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => router.push(`/nurse/tasks/${task.id}/review`)}
                        className="w-full"
                      >
                        查看评估报告
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => router.push(`/nurse/quality/${task.id}`)}
                        className="w-full"
                      >
                        查看AI质量评价
                      </Button>
                    </>
                  )}

                  {task.taskStatus === 'pending_review' && (
                    <Button
                      onClick={() => router.push(`/nurse/tasks/${task.id}/nursing-plan`)}
                      className="w-full"
                    >
                      <ClipboardDocumentCheckIcon className="w-4 h-4 mr-2" />
                      患者画像与护理计划
                    </Button>
                  )}

                  <Button
                    variant="ghost"
                    onClick={() => router.push(`/nurse/monitor/${task.id}`)}
                    className="w-full"
                  >
                    查看任务全过程
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
