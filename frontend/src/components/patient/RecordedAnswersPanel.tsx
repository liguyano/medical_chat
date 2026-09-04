import React from 'react';
import { getStructuredAnswerDisplayValue } from '@/lib/structuredAnswer';
import type { StructuredAnswer } from '@/lib/types';

export function RecordedAnswersPanel({
  answers,
}: {
  answers: StructuredAnswer[];
}) {
  return (
    <section
      className="flex h-full min-h-0 flex-col"
      aria-label="已记录评估信息"
    >
      <div className="shrink-0 border-b border-border p-5">
        <h2 className="text-xl font-bold">已记录信息</h2>
        <p className="mt-2 text-sm text-foreground-muted">
          这里只显示 AI 已经实际写入评估记录的内容。
        </p>
        <p className="mt-3 text-sm">
          当前已记录 <strong className="text-xl text-primary">{answers.length}</strong> 项
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4">
        {answers.length === 0 ? (
          <p className="rounded-xl border border-border bg-white/70 p-3 text-sm text-foreground-muted">
            暂时还没有已记录信息
          </p>
        ) : (
          <ol className="space-y-2">
            {answers.map((answer) => (
              <li
                key={answer.questionId}
                className="rounded-xl border border-border bg-white/70 p-3"
              >
                <p className="text-xs leading-relaxed text-foreground-muted">
                  {answer.questionText}
                </p>
                <p className="mt-1 break-words text-sm font-bold leading-relaxed">
                  {getStructuredAnswerDisplayValue(answer)}
                </p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
