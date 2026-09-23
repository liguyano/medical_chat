'use client';

import { Fragment, useEffect, useState } from 'react';
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
  buildAssessmentRows,
  buildCgaReportSections,
  getAssessmentPatient,
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
    <div className="border-t border-neutral-300 pt-4">
      <h3 className="font-semibold text-neutral-950">{title}</h3>
      {items.length ? (
        <ul className="mt-2 space-y-1.5 text-sm leading-6 text-neutral-800">
          {items.map((item, index) => (
            <li key={`${title}-${index}`} className="flex gap-2">
              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-neutral-500" />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-neutral-500">暂无</p>
      )}
    </div>
  );
}

function formatSex(value?: string): string {
  if (!value) return '—';
  const normalized = value.toLowerCase();
  if (normalized === 'male' || normalized === 'm' || value === '男') return '男';
  if (normalized === 'female' || normalized === 'f' || value === '女') return '女';
  return value;
}

function formatDateTime(value?: string): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function formatDiagnosis(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'string' || typeof value === 'number') return String(value);
  if (Array.isArray(value)) {
    const parts = value.map(formatDiagnosis).filter((item) => item !== '—');
    return parts.length ? parts.join('、') : '—';
  }
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>;
    const preferredKeys = [
      'diagnosis_name',
      'diagnosisName',
      'name',
      'text',
      'diagnosis',
      'admission_diagnosis',
    ];
    for (const key of preferredKeys) {
      if (record[key]) return formatDiagnosis(record[key]);
    }
    const parts = Object.values(record)
      .map(formatDiagnosis)
      .filter((item) => item !== '—');
    return parts.length ? parts.join('、') : '—';
  }
  return String(value);
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
    void careRepository
      .getAssessmentReport(taskId, undefined, controller.signal)
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
  const patientSnapshot = report ? getAssessmentPatient(report) : {};
  const cgaSections = buildCgaReportSections(scaleSnapshots);
  const detailRows = scaleSnapshots.flatMap(buildAssessmentRows);

  const patientName = patientSnapshot.name || task?.patientName || '—';
  const patientSex = formatSex(patientSnapshot.sex || task?.sex);
  const patientAge = patientSnapshot.age ?? task?.age;
  const department = patientSnapshot.department || task?.department || '—';
  const ward = patientSnapshot.ward || task?.wardName || '—';
  const bedNo = patientSnapshot.bed_no || task?.bedNo || '—';
  const inpatientNo = patientSnapshot.inpatient_no || task?.inpatientNo || '—';
  const diagnosis = formatDiagnosis(patientSnapshot.diagnosis);

  return (
    <NurseLayout>
      <div className="mx-auto max-w-7xl space-y-5 print:max-w-none print:space-y-0">
        <div className="flex flex-col gap-3 print:hidden md:flex-row md:items-end md:justify-between">
          <div>
            <Link
              href={`/nurse/tasks/${taskId}`}
              className="mb-2 inline-flex items-center gap-2 text-sm text-foreground-muted"
            >
              <ArrowLeftIcon className="h-4 w-4" /> 返回任务详情
            </Link>
            <h1 className="text-3xl">
              老年综合评估<span className="italic text-primary">（CGA）报告</span>
            </h1>
            <p className="mt-1 text-sm text-foreground-muted">
              以最终确认的量表事实生成纸质报告单式汇总
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
                    第 {version.versionNo} 版 ·{' '}
                    {new Date(version.generatedAt).toLocaleString('zh-CN')}
                  </option>
                ))}
              </select>
              <Button
                variant="outline"
                loading={working}
                onClick={() =>
                  void run(() => careRepository.generateAssessmentReport(taskId, true))
                }
              >
                <ArrowPathIcon className="mr-2 h-4 w-4" /> 重新生成
              </Button>
              {report.reportStatus !== 'confirmed' && (
                <Button
                  loading={working}
                  onClick={() => void run(() => careRepository.confirmAssessmentReport(taskId))}
                >
                  <CheckCircleIcon className="mr-2 h-4 w-4" /> 确认报告
                </Button>
              )}
            </div>
          )}
        </div>

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 print:hidden">
            {error}
          </div>
        )}

        {loading ? (
          <Card padding="lg" className="text-center text-foreground-muted">
            正在加载评估报告...
          </Card>
        ) : !report ? (
          <Card padding="lg" className="py-16 text-center">
            <DocumentTextIcon className="mx-auto h-12 w-12 text-foreground-muted" />
            <h2 className="mt-4 text-xl font-semibold">尚未生成评估报告</h2>
            <p className="mt-2 text-sm text-foreground-muted">
              报告会使用护士最终确认的量表结果，并永久保存为可追溯版本。
            </p>
            <Button
              className="mt-5"
              loading={working}
              onClick={() => void run(() => careRepository.generateAssessmentReport(taskId))}
            >
              <SparklesIcon className="mr-2 h-5 w-5" /> 调用 AI 生成报告
            </Button>
          </Card>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2 text-sm print:hidden">
              <Badge variant={report.reportStatus === 'confirmed' ? 'success' : 'warning'}>
                {report.reportStatus === 'confirmed' ? '护士已确认' : 'AI生成待确认'}
              </Badge>
              <span className="text-foreground-muted">报告编号：{report.reportNo}</span>
              <span className="text-foreground-muted">模型：{report.generatedBy}</span>
              <span className="text-foreground-muted">
                生成于 {new Date(report.generatedAt).toLocaleString('zh-CN')}
              </span>
            </div>

            <article className="overflow-hidden rounded-sm border border-neutral-300 bg-white text-neutral-950 shadow-sm print:border-0 print:shadow-none">
              <div className="px-5 py-8 sm:px-8 lg:px-12 lg:py-10">
                <header className="text-center">
                  <h2 className="text-2xl font-bold tracking-[0.12em] sm:text-3xl">
                    老年综合评估（CGA）报告单
                  </h2>
                  <p className="mt-2 text-sm tracking-widest text-neutral-600">
                    综合护理评估结果
                  </p>
                </header>

                <section className="mt-7 grid gap-x-8 gap-y-2 border-b-2 border-neutral-700 pb-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
                  <p>
                    <span className="text-neutral-500">姓名：</span>
                    <span className="font-medium">{patientName}</span>
                  </p>
                  <p>
                    <span className="text-neutral-500">性别：</span>
                    <span className="font-medium">{patientSex}</span>
                  </p>
                  <p>
                    <span className="text-neutral-500">年龄：</span>
                    <span className="font-medium">
                      {patientAge === null || patientAge === undefined ? '—' : `${patientAge}岁`}
                    </span>
                  </p>
                  <p>
                    <span className="text-neutral-500">住院号：</span>
                    <span className="font-medium">{inpatientNo}</span>
                  </p>
                  <p>
                    <span className="text-neutral-500">病区：</span>
                    <span className="font-medium">{department}</span>
                  </p>
                  <p>
                    <span className="text-neutral-500">病房：</span>
                    <span className="font-medium">{ward}</span>
                  </p>
                  <p>
                    <span className="text-neutral-500">床号：</span>
                    <span className="font-medium">{bedNo}</span>
                  </p>
                  <p>
                    <span className="text-neutral-500">评估编号：</span>
                    <span className="font-medium">{report.reportNo}</span>
                  </p>
                  <p className="sm:col-span-2 lg:col-span-4">
                    <span className="text-neutral-500">入院诊断 / 原因：</span>
                    <span className="font-medium">{diagnosis}</span>
                  </p>
                </section>

                <div className="mt-4 overflow-x-auto">
                  <table className="w-full min-w-[880px] border-collapse text-left text-sm">
                    <thead>
                      <tr className="border-b border-neutral-300 text-xs text-neutral-500">
                        <th className="w-[14%] px-2 py-2 font-medium">评估项目</th>
                        <th className="w-[29%] px-2 py-2 font-medium">相关量表</th>
                        <th className="w-[31%] px-2 py-2 font-medium">评估结果</th>
                        <th className="w-[11%] px-2 py-2 font-medium">责任护士</th>
                        <th className="w-[15%] px-2 py-2 font-medium">评估时间</th>
                      </tr>
                    </thead>
                    <tbody>
                      {cgaSections.map((section) => (
                        <Fragment key={section.id}>
                          <tr>
                            <td
                              colSpan={5}
                              className="border-b border-neutral-300 px-2 pb-1 pt-5 text-base font-semibold"
                            >
                              {section.title}
                            </td>
                          </tr>
                          {section.rows.map((row) => (
                            <tr
                              key={row.id}
                              className="border-b border-neutral-200 align-top last:border-b-0"
                            >
                              <td className="px-2 py-3 font-medium">{row.item}</td>
                              <td className="px-2 py-3 leading-6 text-neutral-700">
                                {row.scaleLabel}
                              </td>
                              <td
                                className={
                                  row.completed
                                    ? 'px-2 py-3 leading-6'
                                    : 'px-2 py-3 leading-6 text-neutral-400'
                                }
                              >
                                {row.result}
                              </td>
                              <td className="px-2 py-3 text-neutral-700">
                                {row.assessor || task?.assignedNurseName || '—'}
                              </td>
                              <td className="px-2 py-3 tabular-nums text-neutral-600">
                                {formatDateTime(row.assessedAt)}
                              </td>
                            </tr>
                          ))}
                        </Fragment>
                      ))}
                    </tbody>
                  </table>
                </div>

                <section className="mt-8 border-t-2 border-neutral-700 pt-5">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h3 className="text-base font-semibold">综合评估摘要（AI 导读）</h3>
                    <span className="text-xs text-neutral-500">
                      生成时间：{formatDateTime(report.generatedAt)}
                    </span>
                  </div>
                  <p className="mt-3 text-sm leading-7 text-neutral-800">
                    {report.reportContent.overallSummary}
                  </p>
                </section>

                <section className="mt-6 grid gap-5 sm:grid-cols-2">
                  <ReportList title="重点发现" items={report.reportContent.keyFindings} />
                  <ReportList title="风险概览" items={report.reportContent.riskOverview} />
                  <ReportList title="护理关注点" items={report.reportContent.nursingFocus} />
                  <ReportList
                    title="复评建议"
                    items={report.reportContent.followUpSuggestions}
                  />
                </section>
              </div>
            </article>

            <section className="space-y-3 print:hidden">
              <div>
                <h2 className="text-xl font-semibold">量表原始明细</h2>
                <p className="mt-1 text-sm text-foreground-muted">
                  以下内容仍直接来自报告生成时保存的结构化评估快照，保留全部题目、患者真实结果、临床得分和关注状态。
                </p>
              </div>

              <Card padding="none" className="overflow-hidden">
                {detailRows.length ? (
                  <div className="overflow-x-auto">
                    <table className="min-w-full border-collapse text-left text-sm">
                      <thead className="bg-surface-muted text-foreground-muted">
                        <tr>
                          <th className="whitespace-nowrap px-5 py-3 font-medium">量表</th>
                          <th className="min-w-52 px-5 py-3 font-medium">评估项目</th>
                          <th className="min-w-48 px-5 py-3 font-medium">患者情况</th>
                          <th className="whitespace-nowrap px-5 py-3 text-center font-medium">
                            得分
                          </th>
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
          </>
        )}
      </div>
    </NurseLayout>
  );
}
