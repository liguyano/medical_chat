import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { VoiceOrb } from '@/components/patient/VoiceOrb';
import { describe, expect, it } from 'vitest';
import { describeVoiceFailure } from '@/lib/patient/voiceFailure';

describe('语音异常提示', () => {
  it('明确麦克风权限和设备问题', () => {
    expect(describeVoiceFailure('microphone', 'NotAllowedError')).toContain('允许麦克风');
    expect(describeVoiceFailure('microphone', 'NotFoundError')).toContain('未找到');
    expect(describeVoiceFailure('microphone', 'NotReadableError')).toContain('占用');
  });
  it('区分上游和浏览器连接，并保留错误码', () => {
    expect(describeVoiceFailure('server', 'VOICE_UPSTREAM_FAILED')).toContain('语音模型');
    expect(describeVoiceFailure('closed', '1006')).toContain('WS_1006');
    expect(describeVoiceFailure('closed', '1006')).toContain('原因待查');
  });
  it('未知服务错误不显示原始消息或推测额度问题', () => {
    const detail = describeVoiceFailure('server', 'SECRET 患者');
    expect(detail).toContain('原因待查');
    expect(detail).not.toContain('SECRET');
    expect(detail).not.toContain('额度');
  });
  it('降级浮层展示具体错误编号', () => {
    const errorMessage = describeVoiceFailure('server', 'VOICE_UPSTREAM_FAILED');
    const html = renderToStaticMarkup(createElement(VoiceOrb, { state: 'text_fallback', errorMessage }));
    expect(html).toContain('VOICE_UPSTREAM_FAILED');
    expect(html).toContain('语音模型');
  });

});
