import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { VoiceDiagnosticsPanel } from '@/components/patient/VoiceDiagnosticsPanel';
import { describe, expect, it } from 'vitest';
import { measurePcm16 } from '@/lib/audio/voiceCaptureStats';
describe('实际PCM采集音量', () => {
  it('区分静音与有能量的帧', () => {
    expect(measurePcm16(new Int16Array([0, 0]).buffer)).toEqual({ rms: 0, peak: 0 });
    expect(measurePcm16(new Int16Array([1000, -1000]).buffer)).toEqual({ rms: 1000, peak: 1000 });
  });
});

it('未启用采集时明确提示，不假装检测成功', () => {
  const html = renderToStaticMarkup(createElement(VoiceDiagnosticsPanel, { data: null }));
  expect(html).toContain('开启语音后显示检测数据');
  expect(html).toContain('麦克风音量');
});
