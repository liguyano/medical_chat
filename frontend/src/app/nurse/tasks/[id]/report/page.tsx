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
  buildAbilitySummaries,
  buildAssessmentRows,
  getAssessmentScales,
} from '@/lib/assessmentReportView';
import {
  ArrowLeftIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  DocumentTextIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline';

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

  const scaleSnapshots = report ? getAssessmentScales(report) : [];
  const abilitySummaries = buildAbilitySummaries(scaleSnapshots);
  const detailRows = scaleSnapshots.flatMap(buildAssessmentRows);

  return (
    <NurseLayout>
      <div className="mx-auto max-w-6xl space-y-5">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <Link href={`/nurse/tasks/${taskId}`} className="mb-2 inline-flex items-center gap-2 text-sm text-foreground-muted">
              <ArrowLeftIcon className="h-4 w-4" /> 返回任务详情
            </Link>
            <h1 className="text-3xl">患者身体状况<span className="italic text-primary">评估报告</span></h1>
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
              <CardHeader>
                <CardTitle>患者身体状况</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm leading-7">{report.reportContent.overallSummary}</p>
              </CardContent>
            </Card>

            <section className="space-y-3">
              <div>
                <h2 className="text-xl font-semibold">各项能力概览</h2>
                <p className="mt-1 text-sm text-foreground-muted">
                  根据本次全部量表结果汇总患者的功能状态、能力水平和风险情况。
                </p>
              </div>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {abilitySummaries.map((ability) => (
                  <Card key={ability.code} padding="md" className="h-full">
                    <div className="flex h-full flex-col gap-3">
                      <div className="flex items-start justify-between gap-3">
                        <h3 className="font-semibold leading-6">{ability.name}</h3>
                        {ability.riskLevel && (
                          <Badge variant="warning">{ability.riskLevel}</Badge>
                        )}
                      </div>
                      <p className="text-lg font-semibold text-primary">
                        {ability.conclusion}
                      </p>
                      {ability.score && (
                        <p className="mt-auto text-sm text-foreground-muted">
                          {ability.score}
                        </p>
                      )}
                    </div>
                  </Card>
                ))}
              </div>
            </section>

            <section className="space-y-3">
              <div>
                <h2 className="text-xl font-semibold">全部评估项目</h2>
                <p className="mt-1 text-sm text-foreground-muted">
                  以下内容来自生成报告时保存的结构化评估快照，展示全部题目和真实结果，不由模型改写。
                </p>
              </div>
              <Card padding="none" className="overflow-hidden">
                {detailRows.length ? (
                  <div className="overflow-x-auto">
                    <table className="min-w-full border-collapse text-left text-sm">
                      <thead className="bg-surface-muted text-foreground-muted">
                        <tr>
                          <th className="whitespace-nowrap px-5 py-3 font-medium">能力分类</th>
                          <th className="min-w-52 px-5 py-3 font-medium">评估项目</th>
                          <th className="min-w-48 px-5 py-3 font-medium">患者情况</th>
                          <th className="whitespace-nowrap px-5 py-3 text-center font-medium">得分</th>
                          <th className="whitespace-nowrap px-5 py-3 font-medium">结果</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {detailRows.map((row) => (
                          <tr
                            key={row.id}
                            className={row.abnormal ? 'bg-amber-50/70' : 'bg-surface'}
                          >
                            <td className="whitespace-nowrap px-5 py-4 text-foreground-muted">
                              {row.ability}
                            </td>
                            <td className="px-5 py-4 font-medium">{row.question}</td>
                            <td className="px-5 py-4">{row.value}</td>
                            <td className="px-5 py-4 text-center tabular-nums">{row.score}</td>
                            <td className="px-5 py-4">
                              <Badge variant={row.abnormal ? 'warning' : 'success'}>
                                {row.status}
                              </Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="p-8 text-center text-sm text-foreground-muted">
                    暂无结构化评估项目
                  </p>
                )}
              </Card>
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
