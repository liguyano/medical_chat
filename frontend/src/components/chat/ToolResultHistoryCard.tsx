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
          <p className="mt-1 text-xs text-foreground-muted">
            文档版本 {item.documentVersion || '未标注'}
            {isEducation && props.item.sourceName
              ? ` · 来源：${props.item.sourceName}`
              : ''}
          </p>
          {isEducation ? (
            <div className="mt-3 space-y-3">
              <div className="rounded-xl border border-sky-100 bg-white p-4">
                <p className="mb-2 text-xs font-medium text-sky-800">宣教原文</p>
                <p className="whitespace-pre-wrap text-sm leading-7">
                  {props.item.originalContent || props.item.patientContent}
                </p>
              </div>
              {props.item.patientContent &&
                props.item.patientContent !== props.item.originalContent && (
                  <div className="rounded-xl bg-sky-100/60 p-3">
                    <p className="mb-1 text-xs font-medium text-sky-900">
                      通俗说明
                    </p>
                    <p className="whitespace-pre-wrap text-sm leading-6">
                      {props.item.patientContent}
                    </p>
                  </div>
                )}
              {props.item.spokenContent &&
                props.item.spokenContent !== props.item.patientContent && (
                  <div className="rounded-xl border border-sky-100 bg-white p-3">
                    <p className="mb-1 text-xs font-medium text-sky-800">
                      播报内容
                    </p>
                    <p className="whitespace-pre-wrap text-sm leading-6">
                      {props.item.spokenContent}
                    </p>
                  </div>
                )}
              <p className="text-xs text-foreground-muted">
                患者操作：
                {props.item.acknowledged ? '已确认阅读' : '尚未确认阅读'}
                {props.item.acknowledgedAt
                  ? ` · ${formatDateTime(props.item.acknowledgedAt)}`
                  : ''}
              </p>
            </div>
          ) : (
            <div className="mt-3 space-y-3">
              {props.item.fullText && (
                <div className="rounded-xl border border-violet-100 bg-white p-4">
                  <p className="mb-2 text-xs font-medium text-violet-800">
                    知情同意全文
                  </p>
                  <p className="whitespace-pre-wrap text-sm leading-7">
                    {props.item.fullText}
                  </p>
                </div>
              )}
              {props.item.clauses.map((clause, index) => (
                <div
                  key={clause.id}
                  className="rounded-xl border border-violet-100 bg-white p-4"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-xs text-foreground-muted">
                        第 {index + 1} 条
                      </p>
                      <p className="mt-1 text-sm font-semibold">
                        {clause.clauseName}
                      </p>
                    </div>
                    {clause.importanceLevel === 'critical' && (
                      <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs text-red-700">
                        必须确认
                      </span>
                    )}
                  </div>
                  <p className="mt-3 whitespace-pre-wrap text-sm leading-7">
                    {clause.patientContent}
                  </p>
                  <p className="mt-3 text-xs text-foreground-muted">
                    患者操作：
                    {clause.confirmed
                      ? '已阅读并确认'
                      : clause.listened
                        ? '已播放/阅读，未确认'
                        : '未完成阅读'}
                  </p>
                </div>
              ))}
              <p className="text-sm text-foreground-muted">
                当前结果：{consentStatusLabel(props.item)}
              </p>
              {props.item.completedAt && (
                <p className="text-xs text-foreground-muted">
                  操作时间：{formatDateTime(props.item.completedAt)}
                </p>
              )}
            </div>
          )}
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

function consentStatusLabel(item: ConsentRequest): string {
  if (item.status === 'signed') return '患者已确认并签署';
  if (item.status === 'refused') return '患者已拒绝';
  if (item.status === 'needs_explanation') return '患者请求护士解释';
  return '待患者确认';
}
