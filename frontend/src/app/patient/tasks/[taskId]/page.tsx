'use client';

import { useParams, useRouter } from 'next/navigation';
import PatientLayout from '@/components/layout/PatientLayout';
import { PatientIcon } from '@/components/patient/PatientIcon';
import { PatientState } from '@/components/patient/PatientState';
import { isPatientTaskReadOnly } from '@/lib/patient/taskGroups';
import { useTaskStore } from '@/lib/stores/useTaskStore';

const contentIcons = ['document', 'user', 'warning', 'shield'] as const;
const contentTones = [
  'bg-[#fff0df] text-[#eb884b]',
  'bg-[#e2f5f5] text-[#45a6a8]',
  'bg-[#eef5dc] text-[#86ad46]',
  'bg-[#eee7fb] text-[#9674c5]',
];

export default function PatientTaskDetailPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const router = useRouter();
  const task = useTaskStore((state) =>
    state.tasks.find((item) => item.id === taskId)
  );

  if (!task) {
    return (
      <PatientLayout title="任务详情" showBack>
        <div className="p-[18px]">
          <PatientState
            kind="empty-tasks"
            title="任务不存在或已经失效"
            description="请返回任务中心查看最新护理任务。"
          />
          <button
            className="patient-primary-button mt-4 w-full"
            onClick={() => router.push('/patient/tasks')}
          >
            返回任务中心
          </button>
        </div>
      </PatientLayout>
    );
  }

  const startPath =
    task.collectionMode === 'ai_dialogue'
      ? `/patient/dialogue/${task.id}`
      : `/patient/form/${task.id}`;
  const canViewDialogue =
    task.collectionMode === 'ai_dialogue' && isPatientTaskReadOnly(task);
  const finished =
    task.taskStatus === 'pending_review' || task.taskStatus === 'completed';
  const content = [
    ...(task.scaleNames?.length
      ? task.scaleNames
      : ['入院基本情况', '日常生活能力', '护理风险']),
  ];

  return (
    <PatientLayout
      title="任务详情"
      showBack
      onBack={() => router.push('/patient/tasks')}
    >
      <div className="space-y-4 px-[18px] pb-8 pt-4">
        <section className="patient-card overflow-hidden p-4">
          <div className="flex items-center gap-3">
            <span className="grid h-14 w-14 shrink-0 place-items-center rounded-full bg-gradient-to-br from-[#ff7658] to-[#ff4f31] text-white">
              <PatientIcon
                name={
                  task.collectionMode === 'ai_dialogue'
                    ? 'nav-assistant'
                    : 'clipboard'
                }
                className="h-8 w-8"
              />
            </span>
            <div className="min-w-0 flex-1">
              <h1 className="truncate text-[26px] font-black">{task.taskType}</h1>
              <p className="mt-0.5 text-sm text-foreground-muted">
                {task.collectionMode === 'ai_dialogue'
                  ? 'AI 对话评估'
                  : '传统问卷评估'}
              </p>
            </div>
          </div>

          <div className="mt-6 grid grid-cols-[1fr_auto_1fr_auto_1fr] items-start">
            {[
              { value: '1', label: '评估', done: finished },
              { value: '2', label: '宣教', done: finished },
              {
                value: '3',
                label: task.consentRequired ? '知情同意' : '完成',
                done: task.taskStatus === 'completed',
              },
            ].map((step, index) => (
              <div key={step.value} className="contents">
                <div className="flex flex-col items-center">
                  <span
                    className={`grid h-9 w-9 place-items-center rounded-full text-sm font-black ${
                      step.done || index === 0
                        ? 'bg-primary text-white'
                        : 'bg-[#eee9e3] text-foreground-muted'
                    }`}
                  >
                    {step.done ? (
                      <PatientIcon name="check-circle" className="h-5 w-5" />
                    ) : (
                      step.value
                    )}
                  </span>
                  <span
                    className={`mt-2 text-sm font-bold ${
                      step.done || index === 0
                        ? 'text-primary'
                        : 'text-foreground-muted'
                    }`}
                  >
                    {step.label}
                  </span>
                </div>
                {index < 2 && (
                  <span
                    className={`mt-[18px] h-0.5 w-full min-w-8 ${
                      step.done ? 'bg-primary' : 'border-t-2 border-dashed border-[#d6ccc3]'
                    }`}
                  />
                )}
              </div>
            ))}
          </div>

          <div className="mt-5 rounded-[20px] border border-[#eadfd6] bg-[#fffdfb] p-4">
            <h2 className="text-[17px] font-black">本次评估包含以下内容</h2>
            <div className="mt-3 space-y-3">
              {content.map((name, index) => (
                <div key={`${name}-${index}`} className="flex items-center gap-3">
                  <span
                    className={`grid h-8 w-8 shrink-0 place-items-center rounded-xl ${contentTones[index % contentTones.length]}`}
                  >
                    <PatientIcon
                      name={contentIcons[index % contentIcons.length]}
                      className="h-[19px] w-[19px]"
                    />
                  </span>
                  <span className="text-[15px] font-medium">{name}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="grid grid-cols-3 divide-x divide-[#d6e3e2] rounded-[20px] bg-gradient-to-r from-[#eef8f8] to-[#f2f8fb] px-2 py-4 text-center">
          {[
            ['pause', '可以暂停', '中途可暂停'],
            ['edit', '可以纠正', '随时修改'],
            ['shield', '护士最终复核', '检查与确认'],
          ].map(([icon, title, detail]) => (
            <div key={title} className="px-1">
              <PatientIcon
                name={icon as 'pause' | 'edit' | 'shield'}
                className="mx-auto h-7 w-7 text-[#3d9ca1]"
              />
              <p className="mt-2 text-[13px] font-black text-[#328e94]">
                {title}
              </p>
              <p className="mt-1 text-[11px] leading-4 text-foreground-muted">
                {detail}
              </p>
            </div>
          ))}
        </section>

        {task.taskStatus === 'pending_review' ? (
          <section className="patient-card bg-[#eef8f5] p-5 text-center">
            <PatientIcon
              name="check-circle"
              className="mx-auto h-10 w-10 text-success"
            />
            <p className="mt-2 text-lg font-black">评估已提交，等待护士复核</p>
            {canViewDialogue && (
              <button
                className="patient-outline-button mt-4 w-full"
                onClick={() => router.push(`/patient/dialogue/${task.id}`)}
              >
                查看对话记录
              </button>
            )}
          </section>
        ) : task.taskStatus === 'completed' ? (
          <div className="space-y-3">
            <button
              className="patient-primary-button w-full"
              onClick={() => router.push(`/patient/complete/${task.id}`)}
            >
              查看完成结果
            </button>
            {canViewDialogue && (
              <button
                className="patient-outline-button w-full"
                onClick={() => router.push(`/patient/dialogue/${task.id}`)}
              >
                查看对话记录
              </button>
            )}
          </div>
        ) : (
          <button
            className="patient-primary-button w-full"
            onClick={() => router.push(startPath)}
          >
            {task.taskStatus === 'in_progress' ? '从上次位置继续' : '开始评估'}
          </button>
        )}
      </div>
    </PatientLayout>
  );
}
