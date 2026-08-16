'use client';

import Link from 'next/link';
import PatientLayout from '@/components/layout/PatientLayout';
import { Card } from '@/components/shared/Card';
import { Badge } from '@/components/shared/Badge';
import { useUserStore } from '@/lib/stores/useUserStore';
import {
  BellAlertIcon,
  BuildingOffice2Icon,
  ChatBubbleLeftRightIcon,
  MapPinIcon,
  PhoneIcon,
} from '@heroicons/react/24/outline';

export default function PatientHomePage() {
  const { user } = useUserStore();

  return (
    <PatientLayout title="住院服务" showNavigation>
      <div className="max-w-xl mx-auto p-4 space-y-5">
        <section className="rounded-3xl bg-gradient-to-br from-primary to-primary-hover text-white p-6 shadow-sm">
          <Badge className="mb-4 bg-white/15 text-white border-white/20">演示数据</Badge>
          <h1 className="text-3xl mb-2">您好，{user?.name ?? '患者'}</h1>
          <p className="text-white/85">欢迎来到心内科一病区，护理团队将协助您完成入院评估。</p>
          <Link
            href="/patient/tasks"
            className="inline-flex mt-5 rounded-full bg-white text-primary px-5 py-2.5 font-medium"
          >
            查看待完成任务
          </Link>
        </section>

        <div className="grid grid-cols-2 gap-3">
          <Card padding="md">
            <MapPinIcon className="w-6 h-6 text-primary mb-3" />
            <h2 className="text-base font-sans font-semibold">病区位置</h2>
            <p className="text-sm text-foreground-muted mt-1">茶水间位于护士站右侧，开水设备24小时开放。</p>
          </Card>
          <Card padding="md">
            <PhoneIcon className="w-6 h-6 text-primary mb-3" />
            <h2 className="text-base font-sans font-semibold">呼叫护士</h2>
            <p className="text-sm text-foreground-muted mt-1">身体不适或需要下床协助时，请先按床旁呼叫铃。</p>
          </Card>
        </div>

        <Card padding="lg">
          <div className="flex items-center gap-3 mb-4">
            <BuildingOffice2Icon className="w-6 h-6 text-primary" />
            <h2 className="text-xl">今日住院指南</h2>
          </div>
          <div className="space-y-3 text-sm">
            {[
              '请保管好腕带，检查和用药前医护人员会再次核对身份。',
              '夜间下床前请先开灯，行动不便时使用呼叫铃。',
              '病区为无烟环境，请勿在卫生间、楼梯间吸烟。',
            ].map((item, index) => (
              <div key={item} className="flex gap-3 rounded-xl bg-surface-secondary p-3">
                <span className="w-6 h-6 rounded-full bg-primary-tint text-primary flex items-center justify-center text-xs font-semibold">
                  {index + 1}
                </span>
                <p className="flex-1">{item}</p>
              </div>
            ))}
          </div>
        </Card>

        <div className="grid grid-cols-2 gap-3">
          <Link href="/patient/tasks">
            <Card hover padding="md" className="h-full">
              <BellAlertIcon className="w-6 h-6 text-primary mb-2" />
              <p className="font-medium">护理任务</p>
              <p className="text-xs text-foreground-muted mt-1">查看评估、宣教与知情同意</p>
            </Card>
          </Link>
          <Link href="/patient/assistant">
            <Card hover padding="md" className="h-full">
              <ChatBubbleLeftRightIcon className="w-6 h-6 text-primary mb-2" />
              <p className="font-medium">住院AI助手</p>
              <p className="text-xs text-foreground-muted mt-1">咨询病区生活和住院流程</p>
            </Card>
          </Link>
        </div>
      </div>
    </PatientLayout>
  );
}
