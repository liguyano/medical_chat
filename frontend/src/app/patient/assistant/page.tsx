'use client';

import { useState } from 'react';
import Image from 'next/image';
import { NurseCallButton } from '@/components/patient/NurseCallButton';
import PatientLayout from '@/components/layout/PatientLayout';
import { PatientIcon } from '@/components/patient/PatientIcon';
import { useTaskStore } from '@/lib/stores/useTaskStore';
import { useUserStore } from '@/lib/stores/useUserStore';

interface AssistantMessage {
  id: number;
  role: 'assistant' | 'patient';
  content: string;
}

const answers: Record<string, string> = {
  开水: '茶水间位于护士站右侧，开水设备24小时开放。使用热水时请注意防烫。',
  微波炉: '微波炉位于病区公共配餐间，请勿加热密封容器或金属餐具。',
  探视: '本原型中的探视时间为每日15:00—17:00，实际安排请以病区通知为准。',
  呼叫铃: '床头和卫生间均设有呼叫铃。身体不适、输液异常或需要下床协助时请及时使用。',
};

const quickQuestions = ['开水房在哪里？', '如何呼叫护士？', '探视时间？'];

export default function PatientAssistantPage() {
  const [input, setInput] = useState('');
  const [voiceHint, setVoiceHint] = useState(false);
  const user = useUserStore((state) => state.user);
  const task = useTaskStore((state) =>
    state.tasks.find(
      (item) =>
        item.patientId === user?.id &&
        item.taskStatus !== 'completed' &&
        item.taskStatus !== 'cancelled'
    )
  );
  const [messages, setMessages] = useState<AssistantMessage[]>([
    {
      id: 1,
      role: 'assistant',
      content:
        '您好！我是小医助手，我可以为您解答住院期间的生活相关问题。',
    },
  ]);

  const send = (content: string) => {
    const text = content.trim();
    if (!text) return;
    const matched = Object.entries(answers).find(([keyword]) =>
      text.includes(keyword)
    );
    const response = matched
      ? matched[1]
      : '这个问题可能涉及专业医疗判断，我无法直接回答。请使用呼叫铃联系护士，由医护人员为您说明。';
    setMessages((current) => [
      ...current,
      { id: Date.now(), role: 'patient', content: text },
      { id: Date.now() + 1, role: 'assistant', content: response },
    ]);
    setInput('');
    setVoiceHint(false);
  };

  return (
    <PatientLayout showNavigation>
      <div className="flex min-h-[calc(100dvh-92px)] flex-col px-[18px] pb-3 pt-7">
        <header className="text-center">
          <h1 className="text-[30px] font-black text-[#4a241c]">住院助手</h1>
          <div className="mt-4 flex min-h-12 items-center justify-center gap-2 rounded-2xl border border-[#f1c9a7] bg-[#fffaf4] px-3 text-[13px] font-bold text-primary">
            <PatientIcon name="shield" className="h-5 w-5" />
            只回答住院生活问题，不提供诊断建议
          </div>
        </header>

        <section
          className="scrollbar-soft mt-5 flex-1 space-y-4 overflow-y-auto pb-4"
          aria-label="住院助手对话"
        >
          {messages.map((message) => (
            <div
              key={message.id}
              className={`flex items-start gap-3 ${
                message.role === 'patient' ? 'flex-row-reverse' : ''
              }`}
            >
              {message.role === 'assistant' ? (
                <Image
                  src="/assets/patient/illustrations/assistant-avatar.webp"
                  alt="小医助手"
                  width={58}
                  height={58}
                  className="h-14 w-14 shrink-0 rounded-full border border-[#f3ceb3] bg-[#fff5ed] object-contain"
                />
              ) : (
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-[#ffe8da] text-primary">
                  <PatientIcon name="user" className="h-5 w-5" />
                </span>
              )}
              <div className={message.role === 'assistant' ? 'max-w-[78%]' : 'max-w-[82%]'}>
                <p
                  className={`mb-1 text-sm font-bold ${
                    message.role === 'assistant'
                      ? 'text-foreground'
                      : 'text-right text-primary'
                  }`}
                >
                  {message.role === 'assistant'
                    ? '小医助手'
                    : user?.name ?? '我'}
                </p>
                <div
                  className={`rounded-[20px] px-4 py-3 text-[15px] leading-7 shadow-sm ${
                    message.role === 'assistant'
                      ? 'rounded-tl-md border border-[#eadfd6] bg-white'
                      : 'rounded-tr-md bg-gradient-to-br from-[#ff7557] to-[#ff5335] text-white'
                  }`}
                >
                  {message.content}
                </div>
              </div>
            </div>
          ))}

          {messages.length === 1 && (
            <div className="patient-card ml-[68px] p-3">
              <p className="mb-2 text-sm text-foreground-muted">您可以问我：</p>
              <div className="space-y-2">
                {quickQuestions.map((question, index) => (
                  <button
                    key={question}
                    type="button"
                    onClick={() => send(question)}
                    className="flex min-h-[52px] w-full items-center gap-3 rounded-2xl border border-[#f0d1ba] bg-[#fffaf5] px-3 text-left text-[15px] font-bold"
                  >
                    <span className="grid h-8 w-8 place-items-center rounded-full bg-[#ffe8da] text-primary">
                      <PatientIcon
                        name={
                          index === 0
                            ? 'hospital'
                            : index === 1
                              ? 'nurse'
                              : 'family'
                        }
                        className="h-[18px] w-[18px]"
                      />
                    </span>
                    <span className="flex-1">{question}</span>
                    <span
                      aria-hidden="true"
                      className="text-2xl leading-none text-foreground-muted"
                    >
                      ›
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>

        {voiceHint && (
          <div
            role="status"
            className="mb-2 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800"
          >
            住院助手语音问答尚未接入后端；入口已保留，请暂时使用文字输入。护理评估语音功能不受影响。
          </div>
        )}

        <div className="patient-card flex items-center gap-2 p-2">
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="输入住院生活问题"
            className="min-h-12 min-w-0 flex-1 rounded-full border border-[#efcdb5] bg-[#fffdfb] px-4 text-[15px] outline-none focus:border-primary"
            onKeyDown={(event) => {
              if (event.key === 'Enter') send(input);
            }}
          />
          {input.trim() ? (
            <button
              type="button"
              onClick={() => send(input)}
              className="patient-touch-button bg-primary text-white"
              aria-label="发送"
            >
              <PatientIcon name="send" />
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setVoiceHint((current) => !current)}
              className="patient-touch-button bg-primary text-white"
              aria-label="语音输入"
              aria-pressed={voiceHint}
            >
              <PatientIcon name="microphone" />
            </button>
          )}
        </div>

        <NurseCallButton
          taskId={task?.id}
          reason="患者在住院助手页面主动呼叫护士"
          className="mt-3 w-full"
        />
      </div>
    </PatientLayout>
  );
}
