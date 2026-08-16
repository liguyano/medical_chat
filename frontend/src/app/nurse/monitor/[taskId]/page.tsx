'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import NurseLayout from '@/components/layout/NurseLayout';
import ChatBubble from '@/components/chat/ChatBubble';
import { Card } from '@/components/shared/Card';
import { Badge } from '@/components/shared/Badge';
import { Button } from '@/components/shared/Button';
import { Progress } from '@/components/shared/Progress';
import { useChatStore } from '@/lib/stores/useChatStore';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import type { MessageFeedback } from '@/lib/types';
import {
  ArrowLeftIcon,
  HandThumbDownIcon,
  HandThumbUpIcon,
  UserPlusIcon,
} from '@heroicons/react/24/outline';

export default function NurseMonitorDetailPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const task = useTaskStore((state) => state.tasks.find((item) => item.id === taskId));
  const resolveHandoff = useTaskStore((state) => state.resolveHandoff);
  const session = useChatStore((state) => state.sessions[taskId]);
  const structuredAnswers = useChatStore((state) => state.structuredAnswers);
  const interactionEvents = useChatStore((state) => state.events);
  const answers = structuredAnswers[taskId] ?? [];
  const events = interactionEvents[taskId] ?? [];
  const feedback = useChatStore((state) => state.feedback);
  const saveFeedback = useChatStore((state) => state.saveFeedback);
  const markEventHandled = useChatStore((state) => state.markEventHandled);
  const [feedbackMessageId, setFeedbackMessageId] = useState<string | null>(null);
  const [comment, setComment] = useState('');

  if (!task) {
    return <NurseLayout><Card padding="lg">任务不存在</Card></NurseLayout>;
  }

  const submitFeedback = (type: MessageFeedback['feedbackType']) => {
    if (!feedbackMessageId) return;
    saveFeedback({
      messageId: feedbackMessageId,
      taskId,
      feedbackType: type,
      issueTags: type === 'dislike' ? ['追问或表达需优化'] : [],
      comment,
      reviewedAt: new Date().toISOString(),
    });
    setFeedbackMessageId(null);
    setComment('');
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
          {task.handoffRequired && (
            <Button variant="danger" onClick={() => resolveHandoff(taskId)}>
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

      <div className="grid grid-cols-1 xl:grid-cols-[230px_minmax(0,1fr)_340px] gap-4 min-h-[70vh]">
        <Card padding="md">
          <h2 className="font-semibold mb-3">任务进度</h2>
          <Progress value={task.progress?.current ?? 0} max={task.progress?.total ?? 12} size="sm" />
          <p className="text-xs text-foreground-muted mt-2">
            {task.progress?.current ?? 0}/{task.progress?.total ?? 12} · {task.currentStage ?? '采集中'}
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

        <Card padding="md" className="overflow-y-auto max-h-[72vh]">
          <h2 className="font-semibold mb-4">对话回放与逐轮反馈</h2>
          {session?.messages.length ? (
            session.messages.map((message) => (
              <div key={message.id} className="group">
                <ChatBubble message={message} showTime animate={false} />
                {message.role === 'ai' && (
                  <div className="flex justify-start gap-2 -mt-3 mb-4 ml-14">
                    <button
                      type="button"
                      onClick={() => {
                        saveFeedback({
                          messageId: message.id,
                          taskId,
                          feedbackType: 'like',
                          issueTags: [],
                          reviewedAt: new Date().toISOString(),
                        });
                      }}
                      className={`p-1.5 rounded-full ${feedback[message.id]?.feedbackType === 'like' ? 'bg-green-100 text-green-700' : 'text-foreground-muted hover:bg-surface-secondary'}`}
                      aria-label="点赞此AI回复"
                    >
                      <HandThumbUpIcon className="w-4 h-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setFeedbackMessageId(message.id)}
                      className={`p-1.5 rounded-full ${feedback[message.id]?.feedbackType === 'dislike' ? 'bg-red-100 text-red-700' : 'text-foreground-muted hover:bg-surface-secondary'}`}
                      aria-label="点踩此AI回复"
                    >
                      <HandThumbDownIcon className="w-4 h-4" />
                    </button>
                  </div>
                )}
              </div>
            ))
          ) : (
            <p className="text-sm text-foreground-muted">该任务尚未产生对话消息。</p>
          )}
        </Card>

        <div className="space-y-4">
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
                  <p className="text-sm font-medium mt-1">{answer.answerText ?? answer.answerNumber}</p>
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
      </div>

      {feedbackMessageId && (
        <div className="fixed inset-0 z-[70] bg-black/30 flex items-center justify-center p-4">
          <Card padding="lg" className="w-full max-w-md">
            <h2 className="text-xl mb-3">标记AI回复问题</h2>
            <textarea
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              rows={4}
              className="w-full rounded-xl border border-border p-3"
              placeholder="例如：追问顺序不合理、表达不够清晰"
            />
            <div className="flex justify-end gap-2 mt-4">
              <Button variant="ghost" onClick={() => setFeedbackMessageId(null)}>取消</Button>
              <Button variant="danger" onClick={() => submitFeedback('dislike')}>保存点踩意见</Button>
            </div>
          </Card>
        </div>
      )}
    </NurseLayout>
  );
}
