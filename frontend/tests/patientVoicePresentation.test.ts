import { describe, expect, it } from 'vitest';
import {
  getVoicePresentation,
  VOICE_PRESENTATIONS,
} from '@/lib/patient/voicePresentation';

describe('患者端语音状态视觉映射', () => {
  it('覆盖语音交互的全部连接状态', () => {
    expect(Object.keys(VOICE_PRESENTATIONS)).toEqual([
      'idle',
      'connecting',
      'listening',
      'transcribing',
      'thinking',
      'speaking',
      'paused',
      'error',
      'text_fallback',
      'closed',
    ]);
  });

  it('为语音异常提供明确的文字保底说明', () => {
    expect(getVoicePresentation('text_fallback')).toMatchObject({
      title: '语音异常，已切换文字',
      color: '#e5a146',
    });
    expect(getVoicePresentation('text_fallback').detail).toContain('文字');
  });

  it('监听和播报状态使用不同文案与颜色', () => {
    const listening = getVoicePresentation('listening');
    const speaking = getVoicePresentation('speaking');

    expect(listening.title).toBe('请说话');
    expect(speaking.title).toBe('AI 正在播报');
    expect(listening.color).not.toBe(speaking.color);
  });
});
