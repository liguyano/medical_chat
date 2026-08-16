'use client';

import { useState, KeyboardEvent } from 'react';
import { Button } from '@/components/shared/Button';
import {
  PaperAirplaneIcon,
  MicrophoneIcon,
  StopIcon,
} from '@heroicons/react/24/outline';

interface ChatInputProps {
  onSend: (message: string) => void;
  onVoiceStart?: () => void;
  onVoiceStop?: () => void;
  placeholder?: string;
  disabled?: boolean;
  isRecording?: boolean;
}

export default function ChatInput({
  onSend,
  onVoiceStart,
  onVoiceStop,
  placeholder = '输入消息...',
  disabled = false,
  isRecording = false,
}: ChatInputProps) {
  const [message, setMessage] = useState('');

  const handleSend = () => {
    if (!message.trim() || disabled) return;
    onSend(message.trim());
    setMessage('');
  };

  const handleKeyPress = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleVoiceToggle = () => {
    if (isRecording) {
      onVoiceStop?.();
    } else {
      onVoiceStart?.();
    }
  };

  return (
    <div className="border-t border-border bg-surface p-4">
      <div className="flex items-end space-x-3">
        {/* 语音按钮 */}
        {(onVoiceStart || onVoiceStop) && (
          <Button
            variant={isRecording ? 'danger' : 'outline'}
            size="md"
            onClick={handleVoiceToggle}
            disabled={disabled}
            className="flex-shrink-0"
            title={isRecording ? '停止录音' : '开始语音'}
          >
            {isRecording ? (
              <StopIcon className="w-5 h-5" />
            ) : (
              <MicrophoneIcon className="w-5 h-5" />
            )}
          </Button>
        )}

        {/* 输入框 */}
        <div className="flex-1 relative">
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder={placeholder}
            disabled={disabled || isRecording}
            rows={1}
            className="w-full px-4 py-3 pr-12 rounded-xl border border-border bg-background resize-none
              text-foreground placeholder:text-foreground-placeholder
              focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent
              transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed
              max-h-32 overflow-y-auto"
            style={{
              minHeight: '48px',
              height: 'auto',
            }}
          />
        </div>

        {/* 发送按钮 */}
        <Button
          onClick={handleSend}
          disabled={disabled || !message.trim() || isRecording}
          className="flex-shrink-0"
          title="发送消息"
        >
          <PaperAirplaneIcon className="w-5 h-5" />
        </Button>
      </div>

      {/* 录音提示 */}
      {isRecording && (
        <div className="mt-3 flex items-center justify-center space-x-2 text-danger">
          <div className="w-2 h-2 bg-danger rounded-full animate-pulse" />
          <span className="text-sm">正在录音...</span>
        </div>
      )}
    </div>
  );
}
