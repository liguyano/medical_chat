'use client';

import { useState } from 'react';
import PatientLayout from '@/components/layout/PatientLayout';
import { Card } from '@/components/shared/Card';
import { Button } from '@/components/shared/Button';
import { Input } from '@/components/shared/Input';
import {
  ChatBubbleLeftRightIcon,
  ExclamationTriangleIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline';

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

export default function PatientAssistantPage() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<AssistantMessage[]>([
    {
      id: 1,
      role: 'assistant',
      content: '您好，我是住院生活助手。您可以询问茶水间、微波炉、探视时间、呼叫铃等病区生活问题。',
    },
  ]);

  const send = (content: string) => {
    const text = content.trim();
    if (!text) return;
    const matched = Object.entries(answers).find(([keyword]) => text.includes(keyword));
    const response = matched
      ? matched[1]
      : '这个问题可能涉及专业医疗判断，我无法直接回答。请使用呼叫铃联系护士，由医护人员为您说明。';
    setMessages((current) => [
      ...current,
      { id: Date.now(), role: 'patient', content: text },
      { id: Date.now() + 1, role: 'assistant', content: response },
    ]);
    setInput('');
  };

  return (
    <PatientLayout title="住院AI助手" showNavigation>
      <div className="max-w-xl mx-auto p-4">
        <div className="rounded-2xl bg-amber-50 border border-amber-200 p-3 flex gap-2 text-sm text-amber-800 mb-4">
          <ExclamationTriangleIcon className="w-5 h-5 flex-shrink-0" />
          本助手只回答住院生活问题，不提供诊断、用药调整或治疗建议。
        </div>

        <Card padding="lg" className="min-h-[55vh]">
          <div className="space-y-4">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex ${message.role === 'patient' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm ${
                    message.role === 'patient'
                      ? 'bg-primary text-white'
                      : 'bg-surface-secondary border border-border'
                  }`}
                >
                  {message.role === 'assistant' && (
                    <div className="flex items-center gap-1 text-xs text-primary mb-1">
                      <SparklesIcon className="w-4 h-4" />
                      住院助手
                    </div>
                  )}
                  {message.content}
                </div>
              </div>
            ))}
          </div>
        </Card>

        <div className="flex flex-wrap gap-2 my-3">
          {['开水房在哪里？', '微波炉在哪里？', '探视时间是什么时候？', '如何呼叫护士？'].map((item) => (
            <button
              key={item}
              onClick={() => send(item)}
              className="rounded-full border border-border bg-surface px-3 py-1.5 text-xs hover:border-primary"
            >
              {item}
            </button>
          ))}
        </div>

        <div className="flex gap-2">
          <Input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="请输入住院生活问题"
            onKeyDown={(event) => {
              if (event.key === 'Enter') send(input);
            }}
          />
          <Button onClick={() => send(input)} title="发送">
            <ChatBubbleLeftRightIcon className="w-5 h-5" />
          </Button>
        </div>
      </div>
    </PatientLayout>
  );
}
