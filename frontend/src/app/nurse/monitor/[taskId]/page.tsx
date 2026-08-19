'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import NurseLayout from '@/components/layout/NurseLayout';
import ChatBubble from '@/components/chat/ChatBubble';
import HandoffHistoryCard from '@/components/chat/HandoffHistoryCard';
import ToolResultHistoryCard from '@/components/chat/ToolResultHistoryCard';
import { Card } from '@/components/shared/Card';
import { Badge } from '@/components/shared/Badge';
import { Button } from '@/components/shared/Button';
import { Progress } from '@/components/shared/Progress';
import { IntegrationStatus } from '@/components/shared/IntegrationStatus';
import { useRealtimeStream } from '@/hooks/useRealtimeStream';
import { abortRequest, isRequestCancelled } from '@/lib/api/httpClient';
import { careRepository } from '@/lib/repositories';
import { runtimeConfig } from '@/lib/runtime/config';
import { useChatStore } from '@/lib/stores/useChatStore';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import { useUserStore } from '@/lib/stores/useUserStore';
import { createMonitorSsePath } from '@/lib/transports/sseClient';
import { applyRealtimeEvent } from '@/lib/transports/applyRealtimeEvent';
import { toHandoffSseEnvelope } from '@/lib/transports/handoffResponse';
import { buildDialogueHistoryTimeline } from '@/lib/dialogue/historyTimeline';
import { getStructuredAnswerDisplayValue } from '@/lib/structuredAnswer';
import type { MessageFeedback } from '@/lib/types';
import { cn } from '@/lib/utils';
import {
  ArrowLeftIcon,
  BellAlertIcon,
  CalendarDaysIcon,
  CheckCircleIcon,
  ClipboardDocumentListIcon,
  HandThumbDownIcon,
  HandThumbUpIcon,
  StarIcon,
  UserPlusIcon,
} from '@heroicons/react/24/outline';

const issueTagOptions = [
  '表达不清晰',
  '信息不准确',
  '漏问关键信息',
  '追问不合理',
  '宣教不适宜',
  '存在安全风险',
];

interface MessageFeedbackDraft {
  score: number | null;
  feedbackType: MessageFeedback['feedbackType'];
  issueTags: string[];
  comment: string;
}

function formatMonitorDate(value?: string): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  });
}

function formatMonitorDateTime(value?: string): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

export default function NurseMonitorDetailPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const task = useTaskStore((state) => state.tasks.find((item) => item.id === taskId));
  const upsertTask = useTaskStore((state) => state.upsertTask);
  const session = useChatStore((state) => state.sessions[taskId]);
  const structuredAnswers = useChatStore((state) => state.structuredAnswers);
  const interactionEvents = useChatStore((state) => state.events);
  const educationCards = useChatStore((state) => state.educationCards);
  const consentRequests = useChatStore((state) => state.consentRequests);
  const nurseAssistanceRequests = useChatStore(
    (state) => state.nurseAssistanceRequests
  );
  const answers = structuredAnswers[taskId] ?? [];
  const events = interactionEvents[taskId] ?? [];
  const pendingHandoffs = Object.values(nurseAssistanceRequests).filter(
    (request) => request.taskId === taskId && request.status === 'requested'
  );
  const feedback = useChatStore((state) => state.feedback);
  const setFeedback = useChatStore((state) => state.setFeedback);
  const saveFeedback = useChatStore((state) => state.saveFeedback);
  const markEventHandled = useChatStore((state) => state.markEventHandled);
  const reviewerId = useUserStore((state) => state.user?.id ?? 'N001');
  const ratingPanelRef = useRef<HTMLDivElement>(null);
  const loadedSnapshotKeyRef = useRef<string | null>(null);
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);
  const [feedbackDrafts, setFeedbackDrafts] = useState<
    Record<string, MessageFeedbackDraft>
  >({});
  const [messageSaving, setMessageSaving] = useState(false);
  const [actionError, setActionError] = useState('');

  useEffect(() => {
    if (runtimeConfig.dataMode !== 'api') return;
    const controller = new AbortController();
    const load = async () => {
      try {
        const currentTask = await careRepository.getTask(
          taskId,
          controller.signal
        );
        upsertTask(currentTask);
        const snapshotKey = `${currentTask.id}:${currentTask.sessionId ?? ''}`;
        if (loadedSnapshotKeyRef.current !== snapshotKey) {
          loadedSnapshotKeyRef.current = snapshotKey;
          const snapshot = await careRepository.getDialogueSnapshot(
            currentTask,
            controller.signal
          );
          useChatStore.getState().setSession(taskId, snapshot.session);
          useChatStore
            .getState()
            .setStructuredAnswers(taskId, snapshot.answers);
          snapshot.events.forEach(applyRealtimeEvent);
        }
        const savedFeedback = await careRepository.listMessageFeedback(
          currentTask.id,
          reviewerId,
          controller.signal
        );
        setFeedback(
          taskId,
          savedFeedback.map((item) => ({ ...item, taskId }))
        );
        setActionError('');
      } catch (loadError) {
        loadedSnapshotKeyRef.current = null;
        if (!controller.signal.aborted && !isRequestCancelled(loadError)) {
          setActionError(
            loadError instanceof Error
              ? `监控数据加载失败：${loadError.message}`
              : '监控数据加载失败'
          );
        }
      }
    };
    void load();
    return () => abortRequest(controller);
  }, [reviewerId, setFeedback, taskId, upsertTask]);

  const aiMessages = session?.messages.filter((message) => message.role === 'ai') ?? [];
  const timeline = useMemo(() => {
    return buildDialogueHistoryTimeline({
      messages: session?.messages,
      educationCards: educationCards[taskId],
      consentRequests: consentRequests[taskId],
      events: interactionEvents[taskId],
    });
  }, [
    consentRequests,
    educationCards,
    interactionEvents,
    session?.messages,
    taskId,
  ]);
  const resolvedSelectedMessageId =
    selectedMessageId && aiMessages.some((message) => message.id === selectedMessageId)
      ? selectedMessageId
      : aiMessages[0]?.id ?? null;
  const selectedMessage = session?.messages.find(
    (message) => message.id === resolvedSelectedMessageId && message.role === 'ai'
  );
  const selectedFeedback = resolvedSelectedMessageId
    ? feedback[resolvedSelectedMessageId]
    : undefined;
  const selectedDraft = resolvedSelectedMessageId
    ? feedbackDrafts[resolvedSelectedMessageId]
    : undefined;
  const messageScore = selectedDraft?.score ?? selectedFeedback?.score ?? null;
  const messageRating =
    selectedDraft?.feedbackType ?? selectedFeedback?.feedbackType ?? 'like';
  const messageTags = selectedDraft?.issueTags ?? selectedFeedback?.issueTags ?? [];
  const messageComment = selectedDraft?.comment ?? selectedFeedback?.comment ?? '';

  const { status: streamStatus, error: streamError } = useRealtimeStream({
    path: task?.sessionId ? createMonitorSsePath(task.sessionId) : undefined,
    enabled: Boolean(task?.sessionId),
  });

  if (!task) {
    return <NurseLayout><Card padding="lg">任务不存在</Card></NurseLayout>;
  }
  const progressStatus =
    task.taskStatus === 'pending_review'
      ? '待复核'
      : task.taskStatus === 'completed'
        ? '已完成'
        : '采集中';

  const updateSelectedDraft = (updates: Partial<MessageFeedbackDraft>) => {
    if (!resolvedSelectedMessageId) return;
    setFeedbackDrafts((current) => {
      const saved = feedback[resolvedSelectedMessageId];
      const base = current[resolvedSelectedMessageId] ?? {
        score: saved?.score ?? null,
        feedbackType: saved?.feedbackType ?? 'like',
        issueTags: saved?.issueTags ?? [],
        comment: saved?.comment ?? '',
      };
      return {
        ...current,
        [resolvedSelectedMessageId]: { ...base, ...updates },
      };
    });
  };

  const submitFeedback = async () => {
    if (!selectedMessage || messageScore === null) return;
    const nextFeedback: MessageFeedback = {
      messageId: selectedMessage.id,
      taskId,
      reviewerId,
      feedbackType: messageRating,
      score: messageScore,
      issueTags: messageTags,
      comment: messageComment.trim() || undefined,
      reviewedAt: new Date().toISOString(),
    };
    setMessageSaving(true);
    try {
      await careRepository.submitMessageFeedback(nextFeedback);
      saveFeedback(nextFeedback);
      setFeedbackDrafts((current) =>
        Object.fromEntries(
          Object.entries(current).filter(([messageId]) => messageId !== selectedMessage.id)
        )
      );
      setActionError('');
    } catch (feedbackError) {
      setActionError(
        feedbackError instanceof Error
          ? feedbackError.message
          : '反馈保存失败'
      );
    } finally {
      setMessageSaving(false);
    }
  };

  const toggleMessageTag = (tag: string) => {
    updateSelectedDraft({
      issueTags: messageTags.includes(tag)
        ? messageTags.filter((item) => item !== tag)
        : [...messageTags, tag],
    });
  };

  const selectScore = (score: number) => {
    updateSelectedDraft({
      score,
      feedbackType: score >= 4 ? 'like' : 'dislike',
    });
  };

  const selectMessage = (messageId: string) => {
    setSelectedMessageId(messageId);
    setActionError('');
    if (window.matchMedia('(max-width: 1279px)').matches) {
      requestAnimationFrame(() => {
        ratingPanelRef.current?.scrollIntoView({
          behavior: 'smooth',
          block: 'start',
        });
      });
    }
  };

  const handleRatingChange = (rating: MessageFeedback['feedbackType']) => {
    updateSelectedDraft({ feedbackType: rating });
  };

  const handleCommentChange = (comment: string) => {
    updateSelectedDraft({ comment });
  };

  const handleResolveHandoff = async () => {
    try {
      const response = await careRepository.resolveHandoff(taskId);
      applyRealtimeEvent(
        toHandoffSseEnvelope(response, {
          taskId,
          sessionId: session?.id,
          eventType: 'handoff_resolved',
        })
      );
      setActionError('');
    } catch (handoffError) {
      setActionError(
        handoffError instanceof Error
          ? handoffError.message
          : '接管操作失败'
      );
    }
  };

  return (
    <NurseLayout>
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <Link href="/nurse/monitor" className="inline-flex items-center gap-2 text-foreground-muted text-sm mb-2">
            <ArrowLeftIcon className="w-4 h-4" />
            返回监控中心
          </Link>
          <h1 className="text-2xl font-semibold">实时监控</h1>
        </div>
        <div className="flex gap-2">
          <IntegrationStatus streamStatus={streamStatus} compact />
          {task.handoffRequired && (
            <Button
              variant="danger"
              onClick={() => void handleResolveHandoff()}
            >
              <UserPlusIcon className="w-5 h-5 mr-2" />
              接管并标记已处理
            </Button>
          )}
          {task.taskStatus === 'pending_review' && (
            <Link href={`/nurse/tasks/${taskId}/review`}>
              <Button>进入护士复核</Button>
            </Link>
          )}
        </div>
      </div>

      <Card padding="md" className="mb-4">
        <div className="flex flex-wrap items-center gap-x-7 gap-y-3">
          <div className="flex items-center gap-3 min-w-[180px]">
            <div className="flex h-11 w-11 items-center justify-center rounded-full bg-orange-100 text-orange-600 text-lg font-semibold">
              {task.patientName.slice(0, 1)}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-lg font-semibold">{task.patientName}</span>
                <Badge variant="success" size="sm">
                  {task.encounterStatus ?? '在院中'}
                </Badge>
              </div>
              <p className="text-xs text-foreground-muted mt-1">
                {task.taskNo} · {task.collectionMode === 'ai_dialogue' ? 'AI 对话采集' : '传统问卷'}
              </p>
            </div>
          </div>
          <div className="hidden h-8 w-px bg-border lg:block" />
          <dl className="grid flex-1 grid-cols-2 gap-x-7 gap-y-2 text-sm sm:grid-cols-3 xl:grid-cols-6">
            <div>
              <dt className="text-xs text-foreground-muted">住院号</dt>
              <dd className="mt-1 font-medium">{task.inpatientNo ?? task.encounterNo ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-xs text-foreground-muted">床位</dt>
              <dd className="mt-1 font-medium">{task.bedNo}</dd>
            </div>
            <div>
              <dt className="text-xs text-foreground-muted">科室</dt>
              <dd className="mt-1 font-medium">{task.department ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-xs text-foreground-muted">性别/年龄</dt>
              <dd className="mt-1 font-medium">{task.sex ?? '—'} / {task.age !== undefined ? `${task.age}岁` : '—'}</dd>
            </div>
            <div>
              <dt className="text-xs text-foreground-muted flex items-center gap-1"><CalendarDaysIcon className="h-3.5 w-3.5" />入院日期</dt>
              <dd className="mt-1 font-medium">{formatMonitorDate(task.admissionDate)}</dd>
            </div>
            <div>
              <dt className="text-xs text-foreground-muted">病区</dt>
              <dd className="mt-1 font-medium">{task.wardName ?? '—'}</dd>
            </div>
          </dl>
        </div>
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(280px,0.95fr)_minmax(0,1.7fr)_minmax(320px,1fr)] gap-4 min-h-[70vh]">
        <div className="min-w-0 space-y-4 xl:sticky xl:top-24 xl:self-start xl:max-h-[72vh] xl:overflow-y-auto xl:pr-1">
          <Card padding="md">
            <div className="flex items-center gap-2 mb-3">
              <ClipboardDocumentListIcon className="h-5 w-5 text-primary" />
              <h2 className="font-semibold">任务概览</h2>
            </div>
            <div className="flex items-end gap-2 mb-2">
              <span className="text-3xl font-semibold text-primary">{task.progress?.current ?? 0}</span>
              <span className="mb-1 text-sm text-foreground-muted">/ {task.progress?.total ?? 0} 项已完成</span>
              <span className="mb-1 text-sm text-foreground-muted">· {progressStatus}</span>
            </div>
            <Progress
              value={task.progress?.current ?? 0}
              max={Math.max(task.progress?.total ?? 0, 1)}
              size="sm"
            />
            <div className="mt-5">
              <p className="text-sm font-medium mb-2">目标量表</p>
              <div className="space-y-2">
                {(task.scaleProgress?.length
                  ? task.scaleProgress
                  : (task.scaleNames ?? []).map((scaleName, index) => ({
                      scaleId: String(index),
                      scaleName,
                      answeredQuestionCount: 0,
                      totalQuestionCount: 0,
                      status: task.taskStatus === 'completed' ? 'completed' as const : index === 0 ? 'collecting' as const : 'pending' as const,
                    }))
                ).map((scale) => (
                  <div key={scale.scaleId} className="flex items-center justify-between gap-2 rounded-xl border border-border px-3 py-2.5 text-sm">
                    <div className="min-w-0">
                      <p className="truncate">{scale.scaleName}</p>
                      {scale.totalQuestionCount > 0 && (
                        <p className="mt-0.5 text-xs text-foreground-muted">
                          {scale.answeredQuestionCount}/{scale.totalQuestionCount} 项
                        </p>
                      )}
                    </div>
                    <Badge
                      variant={scale.status === 'completed' ? 'success' : scale.status === 'collecting' ? 'warning' : 'default'}
                      size="sm"
                    >
                      {scale.status === 'completed' ? '已完成' : scale.status === 'collecting' ? '采集中' : '待采集'}
                    </Badge>
                  </div>
                ))}
              </div>
            </div>
            <div className="mt-5">
              <p className="text-xs text-foreground-muted">连接状态</p>
              <Badge variant={session?.sessionStatus === 'active' ? 'success' : 'default'} size="sm" className="mt-2">
                {session?.sessionStatus === 'active' ? '患者在线' : session?.sessionStatus === 'paused' ? '患者已暂停' : '会话已结束'}
              </Badge>
            </div>
          </Card>

          {task.handoffRequired && pendingHandoffs.length > 0 && (
            <Card padding="md" className="border-red-300 bg-red-50">
              <div className="flex items-center gap-2 text-red-800">
                <UserPlusIcon className="h-5 w-5" />
                <h2 className="font-semibold">患者正在呼叫医护</h2>
              </div>
              <dl className="mt-3 space-y-2 text-sm">
                <div>
                  <dt className="text-xs text-red-700">患者与床位</dt>
                  <dd className="font-medium">
                    {task.patientName} · {task.bedNo}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-red-700">请求操作</dt>
                  <dd className="font-medium">
                    {task.handoffActionLabel ?? '人工护理协助'}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs text-red-700">呼叫原因</dt>
                  <dd>{task.handoffReason}</dd>
                </div>
              </dl>
              <Button
                className="mt-4 w-full"
                variant="danger"
                onClick={() => void handleResolveHandoff()}
              >
                接管并标记已处理
              </Button>
            </Card>
          )}

          <Card padding="md">
            <h2 className="font-semibold mb-3">结构化答案</h2>
            <div className="space-y-2 max-h-72 overflow-y-auto">
              {answers.map((answer) => (
                <div key={answer.questionId} className="rounded-xl bg-surface-secondary p-3">
                  <div className="flex justify-between gap-2">
                    <p className="text-xs text-foreground-muted">{answer.questionText}</p>
                    <Badge variant={answer.extractionConfidence < 0.8 ? 'warning' : 'success'} size="sm">
                      {Math.round(answer.extractionConfidence * 100)}%
                    </Badge>
                  </div>
                  <p className="text-sm font-medium mt-1">
                    {getStructuredAnswerDisplayValue(answer)}
                  </p>
                  <p className="text-xs text-primary mt-1">证据消息 {answer.sourceMessageIds.join(', ')}</p>
                </div>
              ))}
              {!answers.length && <p className="text-sm text-foreground-muted">暂无结构化答案</p>}
            </div>
          </Card>

          <Card padding="md">
            <h2 className="font-semibold mb-3">风险与宣教事件</h2>
            <div className="space-y-2">
              {events.map((event) => (
                <div key={event.id} className="rounded-xl border border-border p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-medium">{event.title}</p>
                      <p className="text-xs text-foreground-muted mt-1">{event.description}</p>
                    </div>
                    <Badge variant={event.priority === 'high' ? 'danger' : 'warning'} size="sm">
                      {event.priority === 'high' ? '高' : '中'}
                    </Badge>
                  </div>
                  <button
                    type="button"
                    onClick={() => markEventHandled(taskId, event.id)}
                    className="mt-2 text-xs text-primary"
                  >
                    {event.handled ? '已处理' : '标记已处理'}
                  </button>
                </div>
              ))}
              {!events.length && <p className="text-sm text-foreground-muted">暂无风险事件</p>}
            </div>
          </Card>

          {session?.aiSummary && (
            <Card padding="md">
              <h2 className="font-semibold mb-2">AI评估总结</h2>
              <p className="text-sm leading-6">{session.aiSummary}</p>
            </Card>
          )}
        </div>

        <Card padding="md" className="overflow-y-auto max-h-[72vh]">
          <div className="flex items-center justify-between gap-3 mb-4">
            <div>
              <h2 className="font-semibold">对话回放</h2>
              <p className="text-xs text-foreground-muted mt-1">
                点击 AI 消息，在右侧完成本轮质评
              </p>
            </div>
            <Badge variant="primary" size="sm">
              {Object.values(feedback).filter((item) => item.taskId === taskId).length} 条已评
            </Badge>
          </div>
          {timeline.length ? (
            timeline.map((item) => {
              if (item.kind === 'event' && item.event.eventType === 'handoff') {
                return (
                  <div key={item.id} className="mb-4">
                    <HandoffHistoryCard event={item.event} />
                  </div>
                );
              }
              if (item.kind === 'education') {
                return (
                  <ToolResultHistoryCard
                    key={item.id}
                    kind="education"
                    item={item.item}
                  />
                );
              }
              if (item.kind === 'consent') {
                return (
                  <ToolResultHistoryCard
                    key={item.id}
                    kind="consent"
                    item={item.item}
                  />
                );
              }
              if (item.kind === 'event') {
                return (
                  <div
                    key={item.id}
                    className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 p-4"
                  >
                    <p className="font-medium">{item.event.title}</p>
                    <p className="mt-1 text-sm">{item.event.description}</p>
                  </div>
                );
              }
              const message = item.message;
              const isAiMessage = message.role === 'ai';
              const isSelected =
                isAiMessage && resolvedSelectedMessageId === message.id;
              const messageFeedback = feedback[message.id];
              return (
              <div
                key={message.id}
                role={isAiMessage ? 'button' : undefined}
                tabIndex={isAiMessage ? 0 : undefined}
                onClick={
                  isAiMessage
                    ? () => selectMessage(message.id)
                    : undefined
                }
                onKeyDown={
                  isAiMessage
                    ? (event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          selectMessage(message.id);
                        }
                      }
                    : undefined
                }
                className={cn(
                  'group rounded-2xl border border-transparent px-2 pt-2 transition-colors',
                  isAiMessage && 'cursor-pointer hover:border-primary/30 hover:bg-primary-tint/30',
                  isSelected && 'border-primary bg-primary-tint/50'
                )}
                aria-pressed={isAiMessage ? isSelected : undefined}
                aria-label={isAiMessage ? `选择第 ${message.turnNo} 轮 AI 消息进行质评` : undefined}
              >
                <ChatBubble message={message} showTime animate={false} />
                {isAiMessage && (
                  <div className="flex items-center gap-2 -mt-3 mb-4 ml-14 text-xs">
                    <span className={isSelected ? 'text-primary font-medium' : 'text-foreground-muted'}>
                      {isSelected ? '正在评价此消息' : '点击评价'}
                    </span>
                    {messageFeedback?.score && (
                      <Badge
                        variant={messageFeedback.score >= 4 ? 'success' : 'warning'}
                        size="sm"
                      >
                        {messageFeedback.score}分
                      </Badge>
                    )}
                  </div>
                )}
              </div>
            );
            })
          ) : (
            <p className="text-sm text-foreground-muted">该任务尚未产生对话消息。</p>
          )}
          {pendingHandoffs.length > 0 && (
            <div className="mt-4 space-y-2">
              {pendingHandoffs.map((request) => (
                <div
                  key={request.requestId}
                  className={cn(
                    'rounded-2xl border p-4',
                    request.requestSource === 'agent'
                      ? 'border-orange-200 bg-orange-50'
                      : 'border-amber-200 bg-amber-50'
                  )}
                >
                  <div className="flex flex-col items-start gap-3 sm:flex-row">
                    <div className={cn(
                      'mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full',
                      request.requestSource === 'agent' ? 'bg-orange-200 text-orange-700' : 'bg-amber-200 text-amber-700'
                    )}>
                      {request.requestSource === 'agent' ? <BellAlertIcon className="h-5 w-5" /> : <UserPlusIcon className="h-5 w-5" />}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold">
                          {request.requestSource === 'agent' ? 'AI 请求护士协助' : '患者主动呼叫护士'}
                        </span>
                        <Badge variant={request.urgency === 'urgent' ? 'danger' : 'warning'} size="sm">
                          {request.urgency === 'urgent' ? '紧急' : '待处理'}
                        </Badge>
                      </div>
                      <p className="mt-1 text-sm">{request.reason}</p>
                      <p className="mt-1 text-xs text-foreground-muted">
                        请求操作：{request.actionLabel} · {formatMonitorDateTime(request.occurredAt)}
                      </p>
                    </div>
                    <Button size="sm" variant="danger" onClick={() => void handleResolveHandoff()}>
                      查看并处理
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <div
          ref={ratingPanelRef}
          className="space-y-4 scroll-mt-24 xl:sticky xl:top-24 xl:self-start xl:max-h-[72vh] xl:overflow-y-auto xl:pr-1"
        >
          <Card padding="md" className="border-primary/30">
            <div className="flex items-start justify-between gap-3 mb-4">
              <div className="flex items-center gap-2">
                <StarIcon className="w-5 h-5 text-primary" />
                <div>
                  <h2 className="font-semibold">本轮 AI 质评</h2>
                  <p className="text-xs text-foreground-muted">评分可随时更新</p>
                </div>
              </div>
              {selectedFeedback?.reviewedAt && (
                <Badge variant="success" size="sm">
                  已保存
                </Badge>
              )}
            </div>

            {selectedMessage ? (
              <div className="space-y-4">
                <div className="rounded-xl bg-surface-secondary p-3">
                  <p className="text-xs text-foreground-muted mb-1">
                    第 {selectedMessage.turnNo} 轮 · AI 消息
                  </p>
                  <p className="text-sm leading-6 line-clamp-4">
                    {selectedMessage.contentText}
                  </p>
                </div>

                <fieldset>
                  <legend className="text-sm font-medium mb-2">
                    质量评分 <span className="text-danger">*</span>
                  </legend>
                  <div className="grid grid-cols-5 gap-2">
                    {[1, 2, 3, 4, 5].map((score) => (
                      <button
                        key={score}
                        type="button"
                        onClick={() => selectScore(score)}
                        className={cn(
                          'h-9 rounded-xl border text-sm font-medium transition-colors',
                          messageScore === score
                            ? 'border-primary bg-primary text-white'
                            : 'border-border bg-surface hover:border-primary hover:text-primary'
                        )}
                        aria-pressed={messageScore === score}
                        aria-label={`评分 ${score} 分`}
                      >
                        {score}
                      </button>
                    ))}
                  </div>
                  <div className="flex justify-between mt-1 text-xs text-foreground-muted">
                    <span>需改进</span>
                    <span>优秀</span>
                  </div>
                </fieldset>

                <div>
                  <p className="text-sm font-medium mb-2">总体判断</p>
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => handleRatingChange('like')}
                      className={cn(
                        'flex items-center justify-center gap-2 rounded-xl border px-3 py-2 text-sm',
                        messageRating === 'like'
                          ? 'border-green-300 bg-green-50 text-green-700'
                          : 'border-border text-foreground-muted'
                      )}
                      aria-pressed={messageRating === 'like'}
                    >
                      <HandThumbUpIcon className="w-4 h-4" />
                      符合预期
                    </button>
                    <button
                      type="button"
                      onClick={() => handleRatingChange('dislike')}
                      className={cn(
                        'flex items-center justify-center gap-2 rounded-xl border px-3 py-2 text-sm',
                        messageRating === 'dislike'
                          ? 'border-red-300 bg-red-50 text-red-700'
                          : 'border-border text-foreground-muted'
                      )}
                      aria-pressed={messageRating === 'dislike'}
                    >
                      <HandThumbDownIcon className="w-4 h-4" />
                      存在问题
                    </button>
                  </div>
                </div>

                <div>
                  <p className="text-sm font-medium mb-2">问题标签（可多选）</p>
                  <div className="flex flex-wrap gap-2">
                    {issueTagOptions.map((tag) => (
                      <button
                        key={tag}
                        type="button"
                        onClick={() => toggleMessageTag(tag)}
                        className={cn(
                          'rounded-full border px-2.5 py-1 text-xs transition-colors',
                          messageTags.includes(tag)
                            ? 'border-primary bg-primary-tint text-primary'
                            : 'border-border text-foreground-muted hover:border-primary'
                        )}
                        aria-pressed={messageTags.includes(tag)}
                      >
                        {tag}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label htmlFor="message-quality-comment" className="text-sm font-medium">
                    自由评价
                  </label>
                  <textarea
                    id="message-quality-comment"
                    value={messageComment}
                    onChange={(event) => handleCommentChange(event.target.value)}
                    rows={3}
                    className="w-full mt-2 rounded-xl border border-border bg-surface p-3 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/10"
                    placeholder="记录具体问题、原因或改进建议"
                  />
                </div>

                <Button
                  className="w-full"
                  loading={messageSaving}
                  disabled={messageScore === null}
                  onClick={() => void submitFeedback()}
                >
                  <CheckCircleIcon className="w-4 h-4 mr-2" />
                  {selectedFeedback ? '更新本轮质评' : '保存本轮质评'}
                </Button>
              </div>
            ) : (
              <div className="rounded-xl bg-surface-secondary p-4 text-sm text-foreground-muted">
                请先在中间对话区选择一条 AI 消息。
              </div>
            )}
          </Card>

        </div>
      </div>

      {(actionError || streamError) && (
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          {actionError || streamError}
        </div>
      )}

    </NurseLayout>
  );
}
