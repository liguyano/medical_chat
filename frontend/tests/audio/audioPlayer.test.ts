import { afterEach, describe, expect, it, vi } from 'vitest';

class FakeSource {
  buffer?: { duration: number };
  onended: (() => void) | null = null;

  connect() {}

  start() {
    setTimeout(() => this.onended?.(), 20);
  }

  stop() {
    this.onended?.();
  }
}

class FakeAudioContext {
  currentTime = 0;
  state: AudioContextState = 'running';
  destination = {};

  createBuffer(_channels: number, length: number, sampleRate: number) {
    return {
      duration: length / sampleRate,
      getChannelData: () => new Float32Array(length),
    };
  }

  createBufferSource() {
    return new FakeSource();
  }

  async resume() {}

  async close() {}
}

describe('Pcm16AudioPlayer', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('等待已排队音频结束并经过静默窗口后才返回', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('AudioContext', FakeAudioContext);
    const { Pcm16AudioPlayer } = await import('@/lib/audio/audioPlayer');
    const player = new Pcm16AudioPlayer();
    await player.enqueue(new Int16Array([1, 2, 3]).buffer);

    let completed = false;
    const waiting = player.waitForIdle(30).then(() => {
      completed = true;
    });
    await vi.advanceTimersByTimeAsync(19);
    expect(completed).toBe(false);
    await vi.advanceTimersByTimeAsync(31);
    await waiting;
    expect(completed).toBe(true);
  });

  it('静默窗口内追加新音频时继续等待新队列排空', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('AudioContext', FakeAudioContext);
    const { Pcm16AudioPlayer } = await import('@/lib/audio/audioPlayer');
    const player = new Pcm16AudioPlayer();
    await player.enqueue(new Int16Array([1]).buffer);

    let completed = false;
    const waiting = player.waitForIdle(30).then(() => {
      completed = true;
    });
    await vi.advanceTimersByTimeAsync(25);
    await player.enqueue(new Int16Array([2]).buffer);
    await vi.advanceTimersByTimeAsync(10);
    expect(completed).toBe(false);
    await vi.advanceTimersByTimeAsync(50);
    await waiting;
    expect(completed).toBe(true);
  });
});
