'use client';

import { useEffect, useRef, useState } from 'react';
import { Badge } from '@/components/shared/Badge';
import { Button } from '@/components/shared/Button';
import type { EducationCard } from '@/lib/types';
import {
  CheckCircleIcon,
  SpeakerWaveIcon,
  StopIcon,
} from '@heroicons/react/24/outline';

interface EducationMaterialCardProps {
  card: EducationCard;
  onAcknowledge: () => void;
}

export default function EducationMaterialCard({
  card,
  onAcknowledge,
}: EducationMaterialCardProps) {
  const autoPlayedRef = useRef(false);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const [speaking, setSpeaking] = useState(false);
  const [speechUnavailable, setSpeechUnavailable] = useState(false);

  const stop = () => {
    if (typeof window === 'undefined' || !('speechSynthesis' in window)) return;
    window.speechSynthesis.cancel();
    setSpeaking(false);
  };

  const play = () => {
    if (
      typeof window === 'undefined' ||
      !('speechSynthesis' in window) ||
      !card.spokenContent
    ) {
      setSpeechUnavailable(true);
      return;
    }
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(card.spokenContent);
    utterance.lang = 'zh-CN';
    utterance.rate = 0.92;
    utterance.onstart = () => setSpeaking(true);
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => {
      setSpeaking(false);
      setSpeechUnavailable(true);
    };
    utteranceRef.current = utterance;
    window.speechSynthesis.speak(utterance);
  };

  useEffect(() => {
    if (!card.autoPlay || autoPlayedRef.current) return;
    autoPlayedRef.current = true;
    play();
    return () => {
      if (
        typeof window !== 'undefined' &&
        utteranceRef.current &&
        window.speechSynthesis.speaking
      ) {
        window.speechSynthesis.cancel();
      }
    };
    // 同一材料只自动播报一次，手动重播由按钮触发。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [card.id]);

  return (
    <section
      className="mb-4 overflow-hidden rounded-2xl border border-sky-200 bg-sky-50"
      aria-label={`医学宣教：${card.title}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-sky-200 px-4 py-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              variant={card.priority === 'high' ? 'danger' : 'info'}
              size="sm"
            >
              医学宣教
            </Badge>
            <span className="text-xs text-foreground-muted">
              v{card.documentVersion}
            </span>
          </div>
          <h2 className="mt-2 font-semibold">{card.title}</h2>
          {card.sourceName && (
            <p className="mt-1 text-xs text-foreground-muted">
              来源：{card.sourceName}
            </p>
          )}
        </div>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={speaking ? stop : play}
        >
          {speaking ? (
            <StopIcon className="mr-1 h-4 w-4" />
          ) : (
            <SpeakerWaveIcon className="mr-1 h-4 w-4" />
          )}
          {speaking ? '停止播报' : '重新播报'}
        </Button>
      </div>

      <div className="space-y-3 p-4">
        <div className="rounded-xl border border-sky-100 bg-white p-4">
          <p className="mb-2 text-xs font-medium text-sky-800">宣教原文</p>
          <p className="whitespace-pre-wrap text-sm leading-7">
            {card.originalContent}
          </p>
        </div>
        {card.patientContent &&
          card.patientContent !== card.originalContent && (
            <details className="rounded-xl bg-sky-100/60 p-3">
              <summary className="cursor-pointer text-sm font-medium text-sky-900">
                查看通俗说明
              </summary>
              <p className="mt-2 text-sm leading-6">{card.patientContent}</p>
            </details>
          )}
        {speechUnavailable && (
          <p className="text-xs text-amber-700">
            当前浏览器未能自动播报，请直接阅读宣教原文。
          </p>
        )}
        {card.requiresAcknowledgement && (
          <Button
            type="button"
            className="w-full"
            variant={card.acknowledged ? 'outline' : 'primary'}
            disabled={card.acknowledged}
            onClick={onAcknowledge}
          >
            <CheckCircleIcon className="mr-2 h-5 w-5" />
            {card.acknowledged ? '已确认阅读' : '我已阅读并了解'}
          </Button>
        )}
      </div>
    </section>
  );
}
