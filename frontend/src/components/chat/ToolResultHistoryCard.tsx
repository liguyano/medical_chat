'use client';

import {
  ClipboardDocumentCheckIcon,
  DocumentTextIcon,
} from '@heroicons/react/24/outline';
import type { ConsentRequest, EducationCard } from '@/lib/types';
import { formatDateTime } from '@/lib/utils';

type ToolResultHistoryCardProps =
  | { kind: 'education'; item: EducationCard }
  | { kind: 'consent'; item: ConsentRequest };

export default function ToolResultHistoryCard(
  props: ToolResultHistoryCardProps
) {
  const isEducation = props.kind === 'education';
  const item = props.item;
  return (
    <div className="mb-4 rounded-2xl border border-sky-200 bg-sky-50/70 p-4">
      <div className="flex items-start gap-3">
        <div className="rounded-xl bg-sky-100 p-2 text-sky-700">
          {isEducation ? (
            <DocumentTextIcon className="h-5 w-5" />
          ) : (
            <ClipboardDocumentCheckIcon className="h-5 w-5" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-semibold">
              {isEducation ? 'AI工具结果 · 医学宣教' : 'AI工具结果 · 知情同意'}
            </p>
            <span className="rounded-full bg-sky-100 px-2 py-0.5 text-xs text-sky-700">
              已执行
            </span>
          </div>
          <p className="mt-1 text-sm font-medium">{item.title}</p>
          <p className="mt-2 text-sm leading-6 text-foreground-muted">
            {isEducation
              ? props.item.patientContent || props.item.originalContent
              : `${props.item.clauses.length} 项条款，当前状态：${props.item.status}`}
          </p>
          {item.toolName && (
            <p className="mt-2 text-xs text-foreground-muted">
              工具：{item.toolName}
              {item.toolResult?.success !== undefined
                ? ` · 结果：${item.toolResult.success ? '成功' : '失败'}`
                : ''}
            </p>
          )}
          <p className="mt-2 text-xs text-foreground-muted">
            {formatDateTime(item.occurredAt)}
          </p>
        </div>
      </div>
    </div>
  );
}
