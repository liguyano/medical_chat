import type { Metadata } from 'next';
import { AssessmentReportDocument } from '@/components/report/AssessmentReportDocument';
import { fullCgaDemoReport } from '@/lib/demo/fullCgaReport';

export const metadata: Metadata = {
  title: 'CGA 完整评估报告示范',
  description: '包含全部固定 CGA 评估项目的独立演示报告。',
};

export default function FullCgaReportDemoPage() {
  return (
    <main className="min-h-screen bg-[#f6f2ec] px-4 py-6 text-foreground sm:px-6 lg:px-10 lg:py-10">
      <div className="mx-auto max-w-7xl space-y-5">
        <header className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 print:hidden">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold tracking-wide text-amber-800">完整演示数据</p>
              <h1 className="mt-1 text-2xl font-semibold text-neutral-950 sm:text-3xl">
                CGA 完整评估报告示范
              </h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-neutral-700">
                本页使用虚构患者资料，固定目录中的 27 个评估项目均已完成，用于展示正式报告的完整形态。
              </p>
            </div>
            <span className="rounded-full border border-amber-300 bg-white px-4 py-2 text-sm font-medium text-amber-800">
              无需登录 · 不读取数据库
            </span>
          </div>
        </header>
        <AssessmentReportDocument report={fullCgaDemoReport} />
      </div>
    </main>
  );
}
