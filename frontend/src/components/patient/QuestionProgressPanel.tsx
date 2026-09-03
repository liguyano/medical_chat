import React from 'react';
import type { QuestionProgress } from '@/lib/types/questionProgress';

const statusLabels = { unasked: '未询问', asked: '已问待确认', recorded: '已记录' };
const statusColors = {
  unasked: 'bg-surface text-foreground-muted',
  asked: 'bg-amber-50 text-amber-800',
  recorded: 'bg-emerald-50 text-emerald-800',
};

export function QuestionProgressPanel({ data, error, onRetry }: {
  data: QuestionProgress | null;
  error: string | null;
  onRetry: () => void;
}) {
  const groups = new Map<string, QuestionProgress['questions']>();
  for (const question of data?.questions ?? []) {
    const group = groups.get(question.scaleName) ?? [];
    group.push(question);
    groups.set(question.scaleName, group);
  }
  const percent = data && data.total > 0
    ? Math.min(100, Math.max(0, Math.round(data.current / data.total * 100))) : 0;
  return (
    <section className="flex h-full min-h-0 flex-col" aria-label="评估题目与进度">
      <div className="shrink-0 border-b border-border p-5">
        <h2 className="text-xl font-bold">评估进度</h2>
        <p className="mt-2 text-sm text-foreground-muted">我们会逐步了解您的情况，您可以随时补充。</p>
        {data && <>
          <p className="my-3 text-sm">已记录必填题 <strong className="text-xl text-primary">{data.current}</strong> / {data.total}</p>
          <div className="patient-progress-track" role="progressbar" aria-label="必填题记录进度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
            <div className="patient-progress-value" style={{ width: `${percent}%` }} />
          </div>
          <p className="mt-2 text-xs text-foreground-muted">仅已确认有效的必填答案计入进度。</p>
        </>}
        {!data && !error && <p className="mt-4 text-sm" role="status">正在加载评估进度…</p>}
        {error && <div className="mt-3 text-sm text-amber-800" role="status">
          <p>{error}</p>
          {data && <p>以下为上次成功更新的进度。</p>}
          <button type="button" onClick={onRetry} className="mt-2 min-h-10 underline underline-offset-4">重新加载</button>
        </div>}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-4" tabIndex={0} aria-label="按量表查看全部评估题目">
        {Array.from(groups, ([name, questions]) => <section key={name} className="mb-5">
          <h3 className="mb-2 text-sm font-bold">{name || '评估题目'}</h3>
          <ol className="space-y-2">
            {questions.map((question) => <li key={question.questionId} aria-current={question.isCurrent ? 'step' : undefined}
              className={`rounded-xl border p-3 ${question.isCurrent ? 'border-primary bg-primary/5 ring-1 ring-primary/20' : 'border-border bg-white/70'}`}>
              <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
                <span className={`rounded-full px-2 py-1 ${statusColors[question.status]}`}>{statusLabels[question.status]}</span>
                {question.isCurrent && <span className="font-bold text-primary">当前题</span>}
              </div>
              <p className="break-words text-sm leading-relaxed">{question.questionText}</p>
            </li>)}
          </ol>
        </section>)}
        {data && data.questions.length === 0 && <p className="text-sm text-foreground-muted">本次评估暂无题目。</p>}
      </div>
    </section>
  );
}
