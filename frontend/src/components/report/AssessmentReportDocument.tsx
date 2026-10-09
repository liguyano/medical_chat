import { Fragment } from 'react';
import { Badge } from '@/components/shared/Badge';
import { Card } from '@/components/shared/Card';
import type { AssessmentReport } from '@/lib/types';
import {
  buildAssessmentRows,
  buildCgaReportSections,
  getAssessmentPatient,
  getAssessmentScales,
} from '@/lib/assessmentReportView';

export interface AssessmentReportFallback {
  patientName?: string;
  sex?: string;
  age?: number;
  department?: string;
  wardName?: string;
  bedNo?: string;
  inpatientNo?: string;
  assignedNurseName?: string;
}

interface AssessmentReportDocumentProps {
  report: AssessmentReport;
  fallback?: AssessmentReportFallback;
  showMeta?: boolean;
  showDetails?: boolean;
}

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
      ) : <p className="mt-2 text-sm text-neutral-500">暂无</p>}
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
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hour12: false,
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
    for (const key of ['diagnosis_name', 'diagnosisName', 'name', 'text', 'diagnosis', 'admission_diagnosis']) {
      if (record[key]) return formatDiagnosis(record[key]);
    }
    const parts = Object.values(record).map(formatDiagnosis).filter((item) => item !== '—');
    return parts.length ? parts.join('、') : '—';
  }
  return String(value);
}

export function AssessmentReportDocument({
  report,
  fallback = {},
  showMeta = true,
  showDetails = true,
}: AssessmentReportDocumentProps) {
  const scales = getAssessmentScales(report);
  const patient = getAssessmentPatient(report);
  const sections = buildCgaReportSections(scales);
  const detailRows = scales.flatMap(buildAssessmentRows);
  const assignedNurse = fallback.assignedNurseName || '—';

  return (
    <div className="space-y-5 print:space-y-0">
      {showMeta && (
        <div className="flex flex-wrap items-center gap-2 text-sm print:hidden">
          <Badge variant={report.reportStatus === 'confirmed' ? 'success' : 'warning'}>
            {report.reportStatus === 'confirmed' ? '护士已确认' : 'AI生成待确认'}
          </Badge>
          <span className="text-foreground-muted">报告编号：{report.reportNo}</span>
          <span className="text-foreground-muted">模型：{report.generatedBy}</span>
          <span className="text-foreground-muted">生成于 {formatDateTime(report.generatedAt)}</span>
        </div>
      )}

      <article className="overflow-hidden rounded-sm border border-neutral-300 bg-white text-neutral-950 shadow-sm print:border-0 print:shadow-none">
        <div className="px-5 py-8 sm:px-8 lg:px-12 lg:py-10">
          <header className="text-center">
            <h2 className="text-2xl font-bold tracking-[0.12em] sm:text-3xl">老年综合评估（CGA）报告单</h2>
            <p className="mt-2 text-sm tracking-widest text-neutral-600">综合护理评估结果</p>
          </header>

          <section className="mt-7 grid gap-x-8 gap-y-2 border-b-2 border-neutral-700 pb-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <p><span className="text-neutral-500">姓名：</span><span className="font-medium">{patient.name || fallback.patientName || '—'}</span></p>
            <p><span className="text-neutral-500">性别：</span><span className="font-medium">{formatSex(patient.sex || fallback.sex)}</span></p>
            <p>
              <span className="text-neutral-500">年龄：</span>
              <span className="font-medium">
                {patient.age ?? fallback.age ? `${patient.age ?? fallback.age}岁` : '—'}
              </span>
            </p>
            <p><span className="text-neutral-500">住院号：</span><span className="font-medium">{patient.inpatient_no || fallback.inpatientNo || '—'}</span></p>
            <p><span className="text-neutral-500">病区：</span><span className="font-medium">{patient.department || fallback.department || '—'}</span></p>
            <p><span className="text-neutral-500">病房：</span><span className="font-medium">{patient.ward || fallback.wardName || '—'}</span></p>
            <p><span className="text-neutral-500">床号：</span><span className="font-medium">{patient.bed_no || fallback.bedNo || '—'}</span></p>
            <p><span className="text-neutral-500">评估编号：</span><span className="font-medium">{report.reportNo}</span></p>
            <p className="sm:col-span-2 lg:col-span-4"><span className="text-neutral-500">入院诊断 / 原因：</span><span className="font-medium">{formatDiagnosis(patient.diagnosis)}</span></p>
          </section>

          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[880px] border-collapse text-left text-sm">
              <thead><tr className="border-b border-neutral-300 text-xs text-neutral-500">
                <th className="w-[14%] px-2 py-2 font-medium">评估项目</th><th className="w-[29%] px-2 py-2 font-medium">相关量表</th><th className="w-[31%] px-2 py-2 font-medium">评估结果</th><th className="w-[11%] px-2 py-2 font-medium">责任护士</th><th className="w-[15%] px-2 py-2 font-medium">评估时间</th>
              </tr></thead>
              <tbody>{sections.map((section) => (
                <Fragment key={section.id}>
                  <tr><td colSpan={5} className="border-b border-neutral-300 px-2 pb-1 pt-5 text-base font-semibold">{section.title}</td></tr>
                  {section.rows.map((row) => (
                    <tr key={row.id} className="border-b border-neutral-200 align-top last:border-b-0">
                      <td className="px-2 py-3 font-medium">{row.item}</td>
                      <td className="px-2 py-3 leading-6 text-neutral-700">{row.scaleLabel}</td>
                      <td className={row.completed ? 'px-2 py-3 leading-6' : 'px-2 py-3 leading-6 text-neutral-400'}>{row.result}</td>
                      <td className="px-2 py-3 text-neutral-700">{row.assessor || assignedNurse}</td>
                      <td className="px-2 py-3 tabular-nums text-neutral-600">{formatDateTime(row.assessedAt)}</td>
                    </tr>
                  ))}
                </Fragment>
              ))}</tbody>
            </table>
          </div>

          <section className="mt-8 border-t-2 border-neutral-700 pt-5">
            <div className="flex flex-wrap items-baseline justify-between gap-2"><h3 className="text-base font-semibold">综合评估摘要（AI 导读）</h3><span className="text-xs text-neutral-500">生成时间：{formatDateTime(report.generatedAt)}</span></div>
            <p className="mt-3 text-sm leading-7 text-neutral-800">{report.reportContent.overallSummary}</p>
          </section>
          <section className="mt-6 grid gap-5 sm:grid-cols-2">
            <ReportList title="重点发现" items={report.reportContent.keyFindings} />
            <ReportList title="风险概览" items={report.reportContent.riskOverview} />
            <ReportList title="护理关注点" items={report.reportContent.nursingFocus} />
            <ReportList title="复评建议" items={report.reportContent.followUpSuggestions} />
          </section>
        </div>
      </article>

      {showDetails && (
        <section className="space-y-3 print:hidden">
          <div><h2 className="text-xl font-semibold">量表原始明细</h2><p className="mt-1 text-sm text-foreground-muted">以下内容直接来自报告快照，保留全部评估题目、患者结果、临床得分和关注状态。</p></div>
          <Card padding="none" className="overflow-hidden">
            <div className="overflow-x-auto"><table className="min-w-full border-collapse text-left text-sm">
              <thead className="bg-surface-muted text-foreground-muted"><tr><th className="whitespace-nowrap px-5 py-3 font-medium">量表</th><th className="min-w-52 px-5 py-3 font-medium">评估项目</th><th className="min-w-48 px-5 py-3 font-medium">患者情况</th><th className="whitespace-nowrap px-5 py-3 text-center font-medium">得分</th><th className="whitespace-nowrap px-5 py-3 font-medium">结果</th></tr></thead>
              <tbody className="divide-y divide-border">{detailRows.map((row) => (
                <tr key={row.id} className={row.abnormal ? 'bg-amber-50/70' : 'bg-surface'}><td className="whitespace-nowrap px-5 py-4 text-foreground-muted">{row.ability}</td><td className="px-5 py-4 font-medium">{row.question}</td><td className="px-5 py-4">{row.value}</td><td className="px-5 py-4 text-center tabular-nums">{row.score}</td><td className="px-5 py-4"><Badge variant={row.abnormal ? 'warning' : 'success'}>{row.status}</Badge></td></tr>
              ))}</tbody>
            </table></div>
          </Card>
        </section>
      )}
    </div>
  );
}
