'use client';

import { useEffect, useRef, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import PatientLayout from '@/components/layout/PatientLayout';
import ChatBubble from '@/components/chat/ChatBubble';
import ChatInput from '@/components/chat/ChatInput';
import { Badge } from '@/components/shared/Badge';
import { Progress } from '@/components/shared/Progress';
import { useChatStore } from '@/lib/stores/useChatStore';
import type {
  CicareStage,
  InteractionMessage,
  InteractionSession,
} from '@/lib/types';
import { SparklesIcon } from '@heroicons/react/24/outline';

interface MockAiResponse {
  cicareStage: CicareStage;
  content: string;
  structuredAnswer?: Record<string, string | number | boolean>;
}

const EMPTY_MESSAGES: InteractionMessage[] = [];

export default function PatientDialoguePage() {
  const { taskId } = useParams<{ taskId: string }>();
  const router = useRouter();
  const { session, addMessage, setSession } = useChatStore();
  const [isLoading, setIsLoading] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [progress, setProgress] = useState({ current: 0, total: 15 });
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messages = session?.messages ?? EMPTY_MESSAGES;

  useEffect(() => {
    if (useChatStore.getState().session?.taskId === taskId) {
      return;
    }

    // 初始化会话
    const timestamp = Date.now();
    const sessionId = `SESSION-${taskId}-${timestamp}`;

    // 添加欢迎消息
    const welcomeMessage: InteractionMessage = {
      id: `MSG-${timestamp}`,
      messageNo: `MSG-${timestamp}`,
      sessionId,
      turnNo: 1,
      role: 'ai',
      cicareStage: 'connect',
      intentType: 'greeting',
      contentText: '您好！我是您的智能护理助手小医。很高兴为您服务，接下来我会通过对话的方式协助您完成入院评估。\n\n评估过程大约需要 10-15 分钟，您可以随时暂停或继续。准备好了吗？',
      occurredAt: new Date().toISOString(),
    };

    const newSession: InteractionSession = {
      id: sessionId,
      sessionNo: sessionId,
      taskId,
      patientId: 'MOCK-PATIENT',
      encounterId: 'MOCK-ENCOUNTER',
      interactionType: 'assessment',
      channelType: 'mixed',
      sessionStatus: 'active',
      startedAt: new Date().toISOString(),
      currentCicareStage: 'connect',
      messages: [welcomeMessage],
    };

    setSession(newSession);
  }, [taskId, setSession]);

  useEffect(() => {
    // 自动滚动到底部
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSendMessage = async (content: string) => {
    if (!session) {
      return;
    }

    // 添加患者消息
    const patientMessage: InteractionMessage = {
      id: `MSG-${Date.now()}`,
      messageNo: `MSG-${Date.now()}`,
      sessionId: session.id,
      turnNo: messages.length + 1,
      role: 'patient',
      cicareStage: session.currentCicareStage,
      intentType: 'answer',
      contentText: content,
      occurredAt: new Date().toISOString(),
    };

    addMessage(patientMessage);
    setIsLoading(true);

    // 模拟 AI 流式回复
    await new Promise((resolve) => setTimeout(resolve, 1000));

    const aiResponses: MockAiResponse[] = [
      {
        cicareStage: 'ask',
        content: '好的，我了解了。请问您今年多大年龄？',
        structuredAnswer: { 准备状态: '已准备' },
      },
      {
        cicareStage: 'ask',
        content: '谢谢。请问您有没有过敏史？比如对某些药物或食物过敏？',
      },
      {
        cicareStage: 'ask',
        content: '明白了。您目前有什么不舒服的症状吗？可以详细描述一下。',
        structuredAnswer: { 年龄: content },
      },
    ];

    const randomResponse = aiResponses[Math.floor(Math.random() * aiResponses.length)];

    const aiMessage: InteractionMessage = {
      id: `MSG-${Date.now() + 1}`,
      messageNo: `MSG-${Date.now() + 1}`,
      sessionId: session.id,
      turnNo: messages.length + 2,
      role: 'ai',
      cicareStage: randomResponse.cicareStage,
      intentType: 'question',
      contentText: randomResponse.content,
      structuredAnswer: randomResponse.structuredAnswer,
      occurredAt: new Date().toISOString(),
    };

    addMessage(aiMessage);
    setIsLoading(false);

    // 更新进度
    setProgress((prev) => ({
      ...prev,
      current: Math.min(prev.current + 1, prev.total),
    }));
  };

  const handleVoiceStart = () => {
    setIsRecording(true);
    // TODO: 实现语音录制
  };

  const handleVoiceStop = () => {
    setIsRecording(false);
    // TODO: 实现语音识别
    handleSendMessage('(语音转文字) 我准备好了');
  };

  return (
    <PatientLayout title="AI 智能评估" showBack onBack={() => router.push('/patient')}>
      <div className="flex flex-col h-[calc(100vh-3.5rem)]">
        {/* 进度条 */}
        <div className="sticky top-0 z-10 bg-surface border-b border-border p-4">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center space-x-2">
              <SparklesIcon className="w-5 h-5 text-primary" />
              <span className="text-sm font-medium text-foreground">智能评估进行中</span>
            </div>
            <Badge variant="primary" size="sm">
              {progress.current} / {progress.total}
            </Badge>
          </div>
          <Progress
            value={progress.current}
            max={progress.total}
            variant="primary"
            size="sm"
          />
        </div>

        {/* 对话区域 */}
        <div className="flex-1 overflow-y-auto p-4 bg-background">
          {messages.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-center">
                <SparklesIcon className="w-16 h-16 text-foreground-muted mx-auto mb-4 opacity-50" />
                <p className="text-foreground-muted">加载中...</p>
              </div>
            </div>
          ) : (
            <>
              {messages.map((message) => (
                <ChatBubble
                  key={message.id}
                  message={message}
                  showAvatar
                  showTime={false}
                  animate
                />
              ))}
              {isLoading && (
                <div className="flex justify-start mb-4">
                  <div className="flex items-center space-x-3">
                    <div className="w-10 h-10 rounded-full bg-primary flex items-center justify-center">
                      <SparklesIcon className="w-5 h-5 text-white" />
                    </div>
                    <div className="bg-surface border border-border rounded-2xl px-4 py-3">
                      <div className="flex space-x-2">
                        <div className="w-2 h-2 bg-foreground-muted rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                        <div className="w-2 h-2 bg-foreground-muted rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                        <div className="w-2 h-2 bg-foreground-muted rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                      </div>
                    </div>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </>
          )}
        </div>

        {/* 输入区域 */}
        <ChatInput
          onSend={handleSendMessage}
          onVoiceStart={handleVoiceStart}
          onVoiceStop={handleVoiceStop}
          placeholder="输入您的回答..."
          disabled={isLoading}
          isRecording={isRecording}
        />
      </div>
    </PatientLayout>
  );
}
