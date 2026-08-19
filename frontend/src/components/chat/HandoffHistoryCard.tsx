'use client';

import { BellAlertIcon, CpuChipIcon, UserIcon } from '@heroicons/react/24/outline';
import type { InteractionEvent } from '@/lib/types';
import { formatDateTime } from '@/lib/utils';

interface HandoffHistoryCardProps {
  event: InteractionEvent;
  compact?: boolean;
}

function text(value: unknown): string {
  return value === undefined || value === null || value === ''
    ? ''
    : String(value);
}

export default function HandoffHistoryCard({
  event,
  compact = false,
}: HandoffHistoryCardProps) {
  const metadata = event.metadata ?? {};
  const requestSource = text(metadata.requestSource) === 'patient'
    ? 'patient'
    : 'agent';
  const isResolved = event.handled;
  const toolResult =
    metadata.toolResult && typeof metadata.toolResult === 'object'
      ? (metadata.toolResult as Record<string, unknown>)
      : undefined;

  return (
    <div
      className={`rounded-2xl border p-4 ${
        requestSource === 'patient'
          ? 'border-amber-200 bg-amber-50/70'
          : 'border-violet-200 bg-violet-50/70'
      }`}
    >
      <div className="flex items-start gap-3">
        <div
          className={`rounded-xl p-2 ${
            requestSource === 'patient'
              ? 'bg-amber-100 text-amber-700'
              : 'bg-violet-100 text-violet-700'
          }`}
        >
          {requestSource === 'patient' ? (
            <UserIcon className="h-5 w-5" />
          ) : (
            <CpuChipIcon className="h-5 w-5" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-semibold">
              {requestSource === 'patient' ? '患者主动呼叫护士' : 'AI工具呼叫护士'}
            </p>
            <span
              className={`rounded-full px-2 py-0.5 text-xs ${
                isResolved
                  ? 'bg-emerald-100 text-emerald-700'
                  : 'bg-red-100 text-red-700'
              }`}
            >
              {isResolved ? '已处理' : '待处理'}
            </span>
          </div>
          <p className="mt-1 text-sm text-foreground-muted">
            {text(metadata.patientName) || '患者'}
            {text(metadata.bedNo) ? ` · ${text(metadata.bedNo)}` : ''}
          </p>
          <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-xs text-foreground-muted">请求时间</dt>
              <dd>{formatDateTime(event.occurredAt)}</dd>
            </div>
            <div>
              <dt className="text-xs text-foreground-muted">请求操作</dt>
              <dd>{text(metadata.actionLabel) || '人工护理协助'}</dd>
            </div>
          </dl>
          <p className="mt-3 text-sm leading-6">
            <span className="text-foreground-muted">原因：</span>
            {event.description}
          </p>
          {toolResult && (
            <p className="mt-2 text-sm leading-6">
              <span className="text-foreground-muted">工具结果：</span>
              {toolResult.success ? '已创建护士协助请求' : text(toolResult.message)}
              {text(toolResult.request_id)
                ? `（请求编号 ${text(toolResult.request_id)}）`
                : ''}
            </p>
          )}
          {isResolved && (
            <div className="mt-3 rounded-xl bg-white/70 p-3 text-sm">
              <p className="font-medium text-emerald-800">处理结果</p>
              <p className="mt-1">
                {text(metadata.resolvedByName) || '护士'}
                {text(metadata.resolvedByStaffNo)
                  ? `（工号 ${text(metadata.resolvedByStaffNo)}）`
                  : ''}
                {text(metadata.handledAt)
                  ? ` · ${formatDateTime(text(metadata.handledAt))}`
                  : ''}
              </p>
              {text(metadata.resolution) && (
                <p className="mt-1 text-foreground-muted">
                  {text(metadata.resolution)}
                </p>
              )}
            </div>
          )}
        </div>
        {!compact && (
          <BellAlertIcon className="h-5 w-5 flex-shrink-0 text-foreground-muted" />
        )}
      </div>
    </div>
  );
}
