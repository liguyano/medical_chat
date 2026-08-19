'use client';

import { motion, type Variants } from 'framer-motion';
import { Badge } from '@/components/shared/Badge';
import type { InteractionMessage } from '@/lib/types';
import { formatDateTime } from '@/lib/utils';
import {
  UserCircleIcon,
  SparklesIcon,
  SpeakerWaveIcon,
  CheckCircleIcon,
} from '@heroicons/react/24/outline';

interface ChatBubbleProps {
  message: InteractionMessage;
  showAvatar?: boolean;
  showTime?: boolean;
  animate?: boolean;
  wide?: boolean;
}

export default function ChatBubble({
  message,
  showAvatar = true,
  showTime = false,
  animate = true,
  wide = false,
}: ChatBubbleProps) {
  const isAI = message.role === 'ai';
  const isPatient = message.role === 'patient';

  const bubbleVariants: Variants = {
    hidden: { opacity: 0, y: 20, scale: 0.95 },
    visible: {
      opacity: 1,
      y: 0,
      scale: 1,
      transition: { duration: 0.3, ease: 'easeOut' },
    },
  };

  const BubbleContent = (
    <div className={`flex ${isPatient ? 'justify-end' : 'justify-start'} mb-4`}>
      <div
        className={`flex ${isPatient ? 'flex-row-reverse' : 'flex-row'} items-start space-x-3 ${
          wide ? 'max-w-[94%]' : 'max-w-[80%]'
        }`}
      >
        {/* 头像 */}
        {showAvatar && (
          <div
            className={`flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center ${
              isAI ? 'bg-primary text-white' : 'bg-surface-secondary text-foreground-muted'
            }`}
          >
            {isAI ? (
              <SparklesIcon className="w-5 h-5" />
            ) : (
              <UserCircleIcon className="w-6 h-6" />
            )}
          </div>
        )}

        {/* 消息内容 */}
        <div className={`flex-1 ${isPatient ? 'mr-3' : 'ml-3'}`}>
          {/* CICARE 阶段标记 */}
          {isAI && message.cicareStage && (
            <div className="mb-2">
              <Badge variant="default" size="sm">
                {getCicareLabel(message.cicareStage)}
              </Badge>
            </div>
          )}

          {/* 气泡 */}
          <div
            className={`rounded-2xl px-4 py-3 ${
              isAI
                ? 'bg-surface border border-border'
                : 'bg-primary text-white'
            }`}
          >
            {/* 文本内容 */}
            {message.contentText && (
              <p className={`text-sm leading-relaxed whitespace-pre-wrap ${
                isAI ? 'text-foreground' : 'text-white'
              }`}>
                {message.contentText}
              </p>
            )}

            {/* 语音标记 */}
            {message.audioUrl && (
              <div className={`flex items-center space-x-2 mt-2 pt-2 border-t ${
                isAI ? 'border-border' : 'border-white/20'
              }`}>
                <SpeakerWaveIcon className={`w-4 h-4 ${isAI ? 'text-foreground-muted' : 'text-white/80'}`} />
                <span className={`text-xs ${isAI ? 'text-foreground-muted' : 'text-white/80'}`}>
                  语音消息
                </span>
              </div>
            )}

            {/* 结构化回答 */}
            {message.structuredAnswer && (
              <div className={`mt-3 pt-3 border-t ${isAI ? 'border-border' : 'border-white/20'}`}>
                {Object.entries(message.structuredAnswer).map(([key, value]) => (
                  <div key={key} className="flex items-start space-x-2 mb-1 last:mb-0">
                    <CheckCircleIcon className={`w-4 h-4 mt-0.5 flex-shrink-0 ${
                      isAI ? 'text-success' : 'text-white'
                    }`} />
                    <div className="flex-1">
                      <span className={`text-xs ${
                        isAI ? 'text-foreground-muted' : 'text-white/80'
                      }`}>
                        {key}:
                      </span>
                      <span className={`text-xs ml-1 ${
                        isAI ? 'text-foreground' : 'text-white'
                      }`}>
                        {String(value)}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 时间戳 */}
          {showTime && (
            <div className={`text-xs text-foreground-muted mt-1 ${
              isPatient ? 'text-right' : 'text-left'
            }`}>
              {formatDateTime(message.occurredAt)}
            </div>
          )}
        </div>
      </div>
    </div>
  );

  if (animate) {
    return (
      <motion.div
        initial="hidden"
        animate="visible"
        variants={bubbleVariants}
      >
        {BubbleContent}
      </motion.div>
    );
  }

  return BubbleContent;
}

function getCicareLabel(stage: string): string {
  const labels: Record<string, string> = {
    connect: 'C 建立联系',
    introduce: 'I 自我介绍',
    communicate: 'C 沟通目的',
    ask: 'A 询问评估',
    respond: 'R 回应需求',
    exit: 'E 结束告别',
  };
  return labels[stage] || stage;
}
