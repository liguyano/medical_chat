'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import NurseLayout from '@/components/layout/NurseLayout';
import ChatBubble from '@/components/chat/ChatBubble';
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
import type { MessageFeedback } from '@/lib/types';
import { cn } from '@/lib/utils';
import {
  ArrowLeftIcon,
  CheckCircleIcon,
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

export default function NurseMonitorDetailPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const task = useTaskStore((state) => state.tasks.find((item) => item.id === taskId));
  const addTask = useTaskStore((state) => state.addTask);
  const resolveHandoff = useTaskStore((state) => state.resolveHandoff);
  const session = useChatStore((state) => state.sessions[taskId]);
  const structuredAnswers = useChatStore((state) => state.structuredAnswers);
  const interactionEvents = useChatStore((state) => state.events);
  const answers = structuredAnswers[taskId] ?? [];
  const events = interactionEvents[taskId] ?? [];
  const feedback = useChatStore((state) => state.feedback);
  const setFeedback = useChatStore((state) => state.setFeedback);
  const saveFeedback = useChatStore((state) => state.saveFeedback);
  const markEventHandled = useChatStore((state) => state.markEventHandled);
  const reviewerId = useUserStore((state) => state.user?.id ?? 'N001');
  const ratingPanelRef = useRef<HTMLDivElement>(null);
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
        const currentTask =
          task ?? (await careRepository.getTask(taskId, controller.signal));
        if (!task) addTask(currentTask);
        if (!useChatStore.getState().sessions[taskId]) {
          const snapshot = await careRepository.getDialogueSnapshot(
            currentTask,
            controller.signal
          );
          useChatStore.getState().setSession(taskId, snapshot.session);
          useChatStore
            .getState()
            .setStructuredAnswers(taskId, snapshot.answers);
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
  }, [addTask, reviewerId, setFeedback, task, taskId]);

  const aiMessages = session?.messages.filter((message) => message.role === 'ai') ?? [];
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
      await careRepository.resolveHandoff(taskId);
      resolveHandoff(taskId);
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
      <div className="mb-5 flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div>
          <Link href="/nurse/monitor" className="inline-flex items-center gap-2 text-foreground-muted text-sm mb-2">
            <ArrowLeftIcon className="w-4 h-4" />
            返回监控中心
          </Link>
          <h1 className="text-3xl">{task.patientName} · {task.bedNo}</h1>
          <p className="text-foreground-muted">{task.taskNo} · {task.collectionMode === 'ai_dialogue' ? 'AI对话采集' : '传统问卷'}</p>
        </div>
        <div className="flex gap-2">
          <IntegrationStatus streamStatus={streamStatus} compact />
          {runtimeConfig.dataMode === 'mock' && task.handoffRequired && (
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

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(280px,0.95fr)_minmax(0,1.7fr)_minmax(320px,1fr)] gap-4 min-h-[70vh]">
        <div className="min-w-0 space-y-4 xl:sticky xl:top-24 xl:self-start xl:max-h-[72vh] xl:overflow-y-auto xl:pr-1">
          <Card padding="md">
            <h2 className="font-semibold mb-3">任务进度</h2>
            <Progress value={task.progress?.current ?? 0} max={task.progress?.total ?? 12} size="sm" />
            <p className="text-xs text-foreground-muted mt-2">
              {task.progress?.current ?? 0}/{task.progress?.total ?? 12} · {progressStatus}
            </p>
            <div className="mt-5 space-y-2">
              {task.scaleNames?.map((name) => (
                <div key={name} className="rounded-xl bg-surface-secondary p-3 text-sm">
                  {name}
                </div>
              ))}
            </div>
            <div className="mt-5">
              <p className="text-xs text-foreground-muted">连接状态</p>
              <Badge variant={session?.sessionStatus === 'active' ? 'success' : 'default'} size="sm" className="mt-2">
                {session?.sessionStatus === 'active' ? '患者在线' : session?.sessionStatus === 'paused' ? '患者已暂停' : '会话已结束'}
              </Badge>
            </div>
          </Card>

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
                    {answer.answerText ??
                      answer.answerNumber ??
                      answer.selectedOptions?.join('、') ??
                      '已记录'}
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
          {session?.messages.length ? (
            session.messages.map((message) => {
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
