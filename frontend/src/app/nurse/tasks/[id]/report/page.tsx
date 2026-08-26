'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import NurseLayout from '@/components/layout/NurseLayout';
import { Badge } from '@/components/shared/Badge';
import { Button } from '@/components/shared/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/shared/Card';
import { careRepository } from '@/lib/repositories';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import type { AssessmentReport } from '@/lib/types';
import {
  ArrowLeftIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  DocumentTextIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline';

interface ScaleSnapshot {
  scale_code?: string;
  scale_name?: string;
  result_summary?: string | null;
  risk_level?: string | null;
  answers?: Array<{
    question?: string;
    value?: unknown;
    clinical_score?: number | null;
    abnormal?: boolean;
  }>;
  scores?: Array<{
    score_name?: string;
    score_value?: number | null;
    max_score?: number | null;
    risk_level?: string | null;
    interpretation?: string | null;
  }>;
}

function assessments(report: AssessmentReport): ScaleSnapshot[] {
  const value = report.sourceSnapshot.assessments;
  return Array.isArray(value) ? (value as ScaleSnapshot[]) : [];
}

function ReportList({ title, items }: { title: string; items: string[] }) {
  return (
    <Card padding="lg">
      <CardHeader><CardTitle>{title}</CardTitle></CardHeader>
      <CardContent>
        {items.length ? (
          <ul className="space-y-2 text-sm leading-6">
            {items.map((item, index) => (
              <li key={`${title}-${index}`} className="flex gap-2">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                <span>{item}</span>
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-foreground-muted">暂无</p>}
      </CardContent>
    </Card>
  );
}

export default function AssessmentReportPage() {
  const { id: taskId } = useParams<{ id: string }>();
  const task = useTaskStore((state) => state.tasks.find((item) => item.id === taskId));
  const [report, setReport] = useState<AssessmentReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    void careRepository.getAssessmentReport(taskId, undefined, controller.signal)
      .then(setReport)
      .catch((cause) => {
        if (!controller.signal.aborted) {
          setError(cause instanceof Error ? cause.message : '评估报告加载失败');
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [taskId]);

  const run = async (action: () => Promise<AssessmentReport>) => {
    setWorking(true);
    setError('');
    try {
      setReport(await action());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '操作失败');
    } finally {
      setWorking(false);
    }
  };

  const selectVersion = async (versionNo: number) => {
    setLoading(true);
    setError('');
    try {
      setReport(await careRepository.getAssessmentReport(taskId, versionNo));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '历史版本加载失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <NurseLayout>
      <div className="mx-auto max-w-6xl space-y-5">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <Link href={`/nurse/tasks/${taskId}`} className="mb-2 inline-flex items-center gap-2 text-sm text-foreground-muted">
              <ArrowLeftIcon className="h-4 w-4" /> 返回任务详情
            </Link>
            <h1 className="text-3xl">量表<span className="italic text-primary">评估报告</span></h1>
            <p className="mt-1 text-sm text-foreground-muted">
              {task ? `${task.patientName} · ${task.bedNo} · ${task.taskNo}` : `任务 ${taskId}`}
            </p>
          </div>
          {report && (
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={report.versionNo}
                onChange={(event) => void selectVersion(Number(event.target.value))}
                className="h-10 rounded-lg border border-border bg-surface px-3 text-sm"
                aria-label="报告历史版本"
              >
                {report.versions.map((version) => (
                  <option key={version.id} value={version.versionNo}>
                    第 {version.versionNo} 版 · {new Date(version.generatedAt).toLocaleString('zh-CN')}
                  </option>
                ))}
              </select>
              <Button variant="outline" loading={working} onClick={() => void run(() => careRepository.generateAssessmentReport(taskId, true))}>
                <ArrowPathIcon className="mr-2 h-4 w-4" /> 重新生成
              </Button>
              {report.reportStatus !== 'confirmed' && (
                <Button loading={working} onClick={() => void run(() => careRepository.confirmAssessmentReport(taskId))}>
                  <CheckCircleIcon className="mr-2 h-4 w-4" /> 确认报告
                </Button>
              )}
            </div>
          )}
        </div>

        {error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</div>}

        {loading ? (
          <Card padding="lg" className="text-center text-foreground-muted">正在加载评估报告...</Card>
        ) : !report ? (
          <Card padding="lg" className="py-16 text-center">
            <DocumentTextIcon className="mx-auto h-12 w-12 text-foreground-muted" />
            <h2 className="mt-4 text-xl font-semibold">尚未生成评估报告</h2>
            <p className="mt-2 text-sm text-foreground-muted">报告会使用护士最终确认的量表结果，并永久保存为可追溯版本。</p>
            <Button className="mt-5" loading={working} onClick={() => void run(() => careRepository.generateAssessmentReport(taskId))}>
              <SparklesIcon className="mr-2 h-5 w-5" /> 调用 AI 生成报告
            </Button>
          </Card>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Badge variant={report.reportStatus === 'confirmed' ? 'success' : 'warning'}>
                {report.reportStatus === 'confirmed' ? '护士已确认' : 'AI生成待确认'}
              </Badge>
              <span className="text-foreground-muted">报告编号：{report.reportNo}</span>
              <span className="text-foreground-muted">模型：{report.generatedBy}</span>
              <span className="text-foreground-muted">生成于 {new Date(report.generatedAt).toLocaleString('zh-CN')}</span>
            </div>

            <Card padding="lg" className="border-primary/20 bg-primary-tint">
              <CardHeader><CardTitle>AI 综合评估结论</CardTitle></CardHeader>
              <CardContent><p className="text-sm leading-7">{report.reportContent.overallSummary}</p></CardContent>
            </Card>

            <section className="space-y-3">
              <div>
                <h2 className="text-xl font-semibold">量表结果</h2>
                <p className="mt-1 text-sm text-foreground-muted">以下内容来自生成报告时保存的结构化评估快照，不由模型改写。</p>
              </div>
              {assessments(report).map((scale, index) => (
                <Card key={scale.scale_code ?? `${scale.scale_name}-${index}`} padding="lg">
                  <CardHeader>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <CardTitle>{scale.scale_name ?? '未命名量表'}</CardTitle>
                      <div className="flex gap-2">
                        {scale.risk_level && <Badge variant="warning">{scale.risk_level}</Badge>}
                        {scale.result_summary && <Badge variant="info">{scale.result_summary}</Badge>}
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {!!scale.scores?.length && (
                      <div className="flex flex-wrap gap-2">
                        {scale.scores.map((score, scoreIndex) => (
                          <Badge key={`${score.score_name}-${scoreIndex}`} variant="info">
                            {score.score_name ?? '得分'}：{score.score_value ?? '—'}{score.max_score != null ? ` / ${score.max_score}` : ''}
                            {score.interpretation ? ` · ${score.interpretation}` : ''}
                          </Badge>
                        ))}
                      </div>
                    )}
                    <div className="divide-y divide-border">
                      {(scale.answers ?? []).map((answer, answerIndex) => (
                        <div key={`${answer.question}-${answerIndex}`} className="grid gap-1 py-2 text-sm md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] md:gap-4">
                          <span>{answer.question ?? '评估项'}</span>
                          <span className="font-medium">{String(answer.value ?? '未记录')}</span>
                          {answer.abnormal ? <Badge variant="warning">异常关注</Badge> : <span />}
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </section>

            <div className="grid gap-4 md:grid-cols-2">
              <ReportList title="重点发现" items={report.reportContent.keyFindings} />
              <ReportList title="风险概览" items={report.reportContent.riskOverview} />
              <ReportList title="护理关注点" items={report.reportContent.nursingFocus} />
              <ReportList title="复评建议" items={report.reportContent.followUpSuggestions} />
            </div>
          </>
        )}
      </div>
    </NurseLayout>
  );
}
