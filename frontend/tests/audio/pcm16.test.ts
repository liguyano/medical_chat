import { describe, expect, it } from 'vitest';
import {
  downsampleFloat32,
  encodePcm16Frame,
  float32ToPcm16,
} from '@/lib/audio/pcm16';

describe('PCM16 audio conversion', () => {
  it('对Float32样本限幅并量化为Int16', () => {
    const pcm = float32ToPcm16(
      new Float32Array([-2, -1, -0.5, 0, 0.5, 1, 2])
    );
    expect(Array.from(pcm)).toEqual([
      -32768, -32768, -16384, 0, 16384, 32767, 32767,
    ]);
  });

  it('将48kHz音频降采样为16kHz', () => {
    const input = new Float32Array(480).fill(0.25);
    const output = downsampleFloat32(input, 48_000, 16_000);
    expect(output).toHaveLength(160);
    expect(output.every((sample) => sample === 0.25)).toBe(true);
    expect(encodePcm16Frame(input, 48_000).byteLength).toBe(320);
  });
});
