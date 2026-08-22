'use client';

import Image from 'next/image';
import { PatientIcon } from '@/components/patient/PatientIcon';
import { runtimeConfig } from '@/lib/runtime/config';
import type { InteractionMessage } from '@/lib/types';

export function PatientChatBubble({
  message,
}: {
  message: InteractionMessage;
}) {
  const isPatient = message.role === 'patient';
  const audioSrc = message.audioUrl
    ? new URL(message.audioUrl, runtimeConfig.apiBaseUrl).toString()
    : undefined;

  return (
    <div
      className={`mb-4 flex items-start gap-2.5 ${
        isPatient ? 'flex-row-reverse' : ''
      }`}
    >
      {isPatient ? (
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#ffe7dc] text-primary">
          <PatientIcon name="user" className="h-5 w-5" />
        </span>
      ) : (
        <Image
          src="/assets/patient/illustrations/assistant-avatar.webp"
          alt="小医"
          width={40}
          height={40}
          className="h-10 w-10 shrink-0 rounded-full border border-[#bce6e2] bg-[#ecf9f7] object-contain"
        />
      )}

      <div className={`max-w-[82%] ${isPatient ? 'text-right' : ''}`}>
        <p
          className={`mb-1 text-xs font-bold ${
            isPatient ? 'text-primary' : 'text-[#2e9893]'
          }`}
        >
          {isPatient ? '我' : '小医'}
        </p>
        <div
          className={`rounded-[18px] px-4 py-3 text-left text-[15px] leading-7 ${
            isPatient
              ? 'rounded-tr-md bg-gradient-to-br from-[#ff7557] to-[#ff5435] text-white'
              : 'rounded-tl-md border border-[#dcebea] bg-[#eff8f7] text-foreground'
          }`}
        >
          {message.contentText && (
            <p className="whitespace-pre-wrap">{message.contentText}</p>
          )}
          {audioSrc && (
            <div
              className={`mt-2 border-t pt-2 ${
                isPatient ? 'border-white/20' : 'border-[#cde2e0]'
              }`}
            >
              <audio
                controls
                preload="metadata"
                src={audioSrc}
                crossOrigin="use-credentials"
                className="h-8 min-w-0 max-w-full"
              />
            </div>
          )}
          {message.isStreaming && (
            <span className="mt-1 inline-flex items-center gap-1 text-xs opacity-70">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
              正在回复
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
