'use client';

import Image from 'next/image';
import { useParams, useRouter } from 'next/navigation';
import PatientLayout from '@/components/layout/PatientLayout';
import { PatientIcon } from '@/components/patient/PatientIcon';
import { useTaskStore } from '@/lib/stores/useTaskStore';

export default function PatientCompletePage() {
  const { taskId } = useParams<{ taskId: string }>();
  const router = useRouter();
  const task = useTaskStore((state) =>
    state.tasks.find((item) => item.id === taskId)
  );
  const consent = useTaskStore((state) => state.consents[taskId]);

  return (
    <PatientLayout showNavigation>
      <div className="px-[18px] pb-6 pt-7 text-center">
        <Image
          src="/assets/patient/illustrations/assessment-complete.webp"
          alt="评估完成"
          width={512}
          height={512}
          priority
          className="mx-auto h-auto w-[270px] object-contain"
        />

        <h1 className="mt-1 text-[36px] font-black text-[#3e241c]">评估已完成</h1>
        <p className="mt-2 text-[16px] text-foreground-muted">
          感谢您的配合，结果已提交护士复核
        </p>

        <div className="mt-5 space-y-3 text-left">
          {[
            {
              icon: 'nurse' as const,
              title: '护士会复核',
              detail: '护士会尽快查看并复核您的评估结果。',
              tone: 'bg-[#e5f5f1] text-[#329879]',
            },
            {
              icon: 'phone' as const,
              title: '有需要会再次联系您',
              detail: '如评估中发现需要关注的情况，我们会再次与您联系。',
              tone: 'bg-[#eaf8ed] text-[#3dad82]',
            },
            {
              icon: 'bell' as const,
              title: '身体不适请按铃',
              detail: '如您感到不适或需要帮助，请立即按床旁呼叫铃。',
              tone: 'bg-[#fff0e7] text-primary',
            },
          ].map((item) => (
            <section
              key={item.title}
              className="patient-card flex min-h-[86px] items-center gap-3 px-4 py-3"
            >
              <span
                className={`grid h-12 w-12 shrink-0 place-items-center rounded-full ${item.tone}`}
              >
                <PatientIcon name={item.icon} className="h-6 w-6" />
              </span>
              <div>
                <h2 className="text-[17px] font-black">{item.title}</h2>
                <p className="mt-1 text-[13px] leading-5 text-foreground-muted">
                  {item.detail}
                </p>
              </div>
            </section>
          ))}
        </div>

        <button
          type="button"
          onClick={() => router.push('/patient/home')}
          className="patient-primary-button mt-5 w-full"
        >
          返回住院服务
        </button>
        <button
          type="button"
          onClick={() => router.push('/patient/tasks')}
          className="patient-outline-button mt-3 w-full"
        >
          查看评估记录
        </button>

        <div className="mt-4 rounded-2xl bg-[#fffaf5] px-4 py-3 text-left text-xs leading-5 text-foreground-muted">
          <p>任务编号：{task?.taskNo ?? taskId}</p>
          <p className="mt-1">
            {task?.consentRequired
              ? consent?.decision === 'agreed'
                ? '知情同意：已确认并完成签名'
                : '知情同意：等待护士进一步处理'
              : '本任务不要求知情同意签名'}
          </p>
        </div>
      </div>
    </PatientLayout>
  );
}
