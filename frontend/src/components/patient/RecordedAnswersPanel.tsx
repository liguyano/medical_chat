import React from 'react';
import { getStructuredAnswerDisplayValue } from '@/lib/structuredAnswer';
import type { StructuredAnswer } from '@/lib/types';

function isManualReviewPending(answer: StructuredAnswer): boolean {
  return (
    answer.collectionStatus === 'manual_review_pending' ||
    answer.displayValue === '待护士人工审核'
  );
}

function isVisibleProcessedItem(answer: StructuredAnswer): boolean {
  if (
    isManualReviewPending(answer) ||
    answer.collectionStatus === 'manual_review_completed'
  ) {
    return true;
  }
  if (answer.collectionStatus === 'pending') return false;
  return Boolean(
    answer.displayValue ||
      answer.answerText !== undefined ||
      answer.answerNumber !== undefined ||
      answer.answerBoolean !== undefined ||
      answer.selectedOptions?.length ||
      answer.invalid
  );
}

function answerStatusText(answer: StructuredAnswer): string {
  if (isManualReviewPending(answer)) {
    return '待护士人工审核';
  }
  if (answer.collectionStatus === 'manual_review_completed') {
    const value = getStructuredAnswerDisplayValue(answer);
    return value ? `${value} · 护士已审核` : '护士已审核';
  }
  return getStructuredAnswerDisplayValue(answer);
}

export function RecordedAnswersPanel({
  answers,
}: {
  answers: StructuredAnswer[];
}) {
  const visibleAnswers = answers.filter(isVisibleProcessedItem);

  return (
    <section
      className="flex h-full min-h-0 flex-col"
      aria-label="已记录评估信息"
    >
      <div className="shrink-0 border-b border-border p-5">
        <h2 className="text-xl font-bold">已记录信息</h2>
        <p className="mt-2 text-sm text-foreground-muted">
          显示 AI 已记录信息，以及从评估开始就指定由护士人工审核的条目。
        </p>
        <p className="mt-3 text-sm">
          当前已处理 <strong className="text-xl text-primary">{visibleAnswers.length}</strong> 项
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4">
        {visibleAnswers.length === 0 ? (
          <p className="rounded-xl border border-border bg-white/70 p-3 text-sm text-foreground-muted">
            暂时还没有已记录信息
          </p>
        ) : (
          <ol className="space-y-2">
            {visibleAnswers.map((answer) => (
              <li
                key={answer.questionId}
                className="rounded-xl border border-border bg-white/70 p-3"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="text-xs leading-relaxed text-foreground-muted">
                    {answer.questionText}
                  </p>
                  {isManualReviewPending(answer) && (
                    <span className="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-700">
                      人工审核
                    </span>
                  )}
                </div>
                <p className="mt-1 break-words text-sm font-bold leading-relaxed">
                  {answerStatusText(answer)}
                </p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
