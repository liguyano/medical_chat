import React from 'react';
import {
  getStructuredAnswerDisplayValue,
  isStructuredAnswerRecorded,
} from '@/lib/structuredAnswer';
import type { StructuredAnswer } from '@/lib/types';

function QuestionList({
  answers,
  showValue,
}: {
  answers: StructuredAnswer[];
  showValue: boolean;
}) {
  if (answers.length === 0) return null;
  return (
    <ol className="space-y-2">
      {answers.map((answer) => (
        <li
          key={answer.questionId}
          className="rounded-xl border border-border bg-white/70 p-3"
        >
          <p className="break-words text-sm leading-relaxed">
            {answer.questionText}
          </p>
          {showValue && (
            <p className="mt-1 break-words text-sm font-bold leading-relaxed text-primary">
              {getStructuredAnswerDisplayValue(answer)}
            </p>
          )}
        </li>
      ))}
    </ol>
  );
}

export function RecordedAnswersPanel({
  answers,
}: {
  answers: StructuredAnswer[];
}) {
  const recorded = answers.filter(isStructuredAnswerRecorded);
  const askedPending = answers.filter(
    (answer) => !isStructuredAnswerRecorded(answer) && Boolean(answer.asked)
  );
  const unasked = answers.filter(
    (answer) => !isStructuredAnswerRecorded(answer) && !answer.asked
  );

  return (
    <section
      className="flex h-full min-h-0 flex-col"
      aria-label="评估题目状态"
    >
      <div className="shrink-0 border-b border-border p-5">
        <h2 className="text-xl font-bold">评估信息</h2>
        <p className="mt-2 text-sm text-foreground-muted">
          AI 能明确对应的回答才会记录；未记录题会继续保留。
        </p>
        {answers.length > 0 && (
          <p className="mt-3 text-sm">
            已记录 <strong className="text-xl text-primary">{recorded.length}</strong>
            {' / '}
            {answers.length}
          </p>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4">
        {answers.length === 0 ? (
          <p className="rounded-xl border border-border bg-white/70 p-3 text-sm text-foreground-muted">
            暂时没有评估题目信息
          </p>
        ) : (
          <div className="space-y-5">
            <section>
              <h3 className="mb-2 text-sm font-bold text-emerald-800">
                已记录（{recorded.length}）
              </h3>
              <QuestionList answers={recorded} showValue />
            </section>

            <section>
              <h3 className="mb-2 text-sm font-bold text-amber-800">
                已问未记录（{askedPending.length}）
              </h3>
              {askedPending.length > 0 ? (
                <QuestionList answers={askedPending} showValue={false} />
              ) : (
                <p className="text-xs text-foreground-muted">暂无</p>
              )}
            </section>

            <section>
              <h3 className="mb-2 text-sm font-bold text-foreground-muted">
                还没问（{unasked.length}）
              </h3>
              {unasked.length > 0 ? (
                <QuestionList answers={unasked} showValue={false} />
              ) : (
                <p className="text-xs text-foreground-muted">暂无</p>
              )}
            </section>
          </div>
        )}
      </div>
    </section>
  );
}
