import { afterEach, describe, expect, it, vi } from 'vitest';

class FakeTrack extends EventTarget {
  readyState = 'live';
  stop = vi.fn(() => { this.readyState = 'ended'; });
  endUnexpectedly() { this.readyState = 'ended'; this.dispatchEvent(new Event('ended')); }
}

class FakeMediaStream {
  track = new FakeTrack();

  getTracks() {
    return [this.track];
  }
}

class FakeProcessor {
  onaudioprocess: ((event: AudioProcessingEvent) => void) | null = null;

  connect() {}

  disconnect() {}
}

class FakeAudioContext {
  state: AudioContextState = 'running';
  sampleRate = 16_000;
  currentTime = 0;
  destination = {};

  async resume() {}

  createMediaStreamSource() {
    return { connect() {}, disconnect() {} };
  }

  createScriptProcessor() {
    return new FakeProcessor();
  }

  createBuffer(_channels: number, length: number, sampleRate: number) {
    return {
      duration: length / sampleRate,
      getChannelData: () => new Float32Array(length),
    };
  }

  createBufferSource() {
    return {
      buffer: undefined,
      onended: null as (() => void) | null,
      connect() {},
      start() {
        this.onended?.();
      },
      stop() {
        this.onended?.();
      },
    };
  }

  async close() {}
}

class FakeWebSocket {
  static OPEN = 1;
  static instances: FakeWebSocket[] = [];
  readyState = FakeWebSocket.OPEN;
  binaryType = '';
  sent: unknown[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number; wasClean: boolean }) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(url: string) {
    void url;
    FakeWebSocket.instances.push(this);
    queueMicrotask(() => this.onopen?.());
  }

  send(value: unknown) {
    this.sent.push(value);
  }

  close() {
    this.readyState = 3;
    this.onclose?.({ code: 1000, wasClean: true });
  }
}

describe('VoiceSocketClient', () => {
  afterEach(() => {
    FakeWebSocket.instances = [];
    vi.unstubAllGlobals();
  });

  it('收到服务端 closed 时停止麦克风并进入关闭状态', async () => {
    const stream = new FakeMediaStream();
    vi.stubGlobal('navigator', {
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue(stream),
      },
    });
    vi.stubGlobal('AudioContext', FakeAudioContext);
    vi.stubGlobal('WebSocket', FakeWebSocket);
    const states: string[] = [];
    const { VoiceSocketClient } = await import(
      '@/lib/transports/voiceSocket'
    );
    const client = new VoiceSocketClient({
      taskId: '111',
      sessionId: 'SESS-111',
      onStateChange: (state) => states.push(state),
    });

    await client.start();
    FakeWebSocket.instances[0]?.onmessage?.({
      data: JSON.stringify({ type: 'closed' }),
    });
    await new Promise((resolve) => setTimeout(resolve, 350));

    expect(stream.track.stop).toHaveBeenCalledOnce();
    expect(states.at(-1)).toBe('closed');
  });

  it('主动关闭发送 close 控制消息并停止麦克风', async () => {
    const stream = new FakeMediaStream();
    vi.stubGlobal('navigator', {
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue(stream),
      },
    });
    vi.stubGlobal('AudioContext', FakeAudioContext);
    vi.stubGlobal('WebSocket', FakeWebSocket);
    const { VoiceSocketClient } = await import(
      '@/lib/transports/voiceSocket'
    );
    const client = new VoiceSocketClient({
      taskId: '111',
      sessionId: 'SESS-111',
    });

    await client.start();
    const socket = FakeWebSocket.instances[0];
    await client.close();

    expect(stream.track.stop).toHaveBeenCalledOnce();
    expect(socket?.sent).toContain(JSON.stringify({ type: 'close' }));
  });

  it('任务完成关闭会等待服务端 response_completed 标记', async () => {
    const stream = new FakeMediaStream();
    vi.stubGlobal('navigator', {
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue(stream),
      },
    });
    vi.stubGlobal('AudioContext', FakeAudioContext);
    vi.stubGlobal('WebSocket', FakeWebSocket);
    const { VoiceSocketClient } = await import(
      '@/lib/transports/voiceSocket'
    );
    const client = new VoiceSocketClient({
      taskId: '111',
      sessionId: 'SESS-111',
    });

    await client.start();
    const socket = FakeWebSocket.instances[0];
    socket?.onmessage?.({
      data: JSON.stringify({ type: 'state', state: 'thinking' }),
    });
    let closed = false;
    const closing = client.finishAndCloseAfterPlayback().then(() => {
      closed = true;
    });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(closed).toBe(false);

    socket?.onmessage?.({
      data: JSON.stringify({
        type: 'response_completed',
        response_id: 'resp-final',
      }),
    });
    await closing;

    expect(closed).toBe(true);
    expect(socket?.sent).toContain(JSON.stringify({ type: 'close' }));
  });

  it('语音网络错误会停止麦克风并切换文字降级', async () => {
    const stream = new FakeMediaStream();
    vi.stubGlobal('navigator', {
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue(stream),
      },
    });
    vi.stubGlobal('AudioContext', FakeAudioContext);
    vi.stubGlobal('WebSocket', FakeWebSocket);
    const states: string[] = [];
    const { VoiceSocketClient } = await import(
      '@/lib/transports/voiceSocket'
    );
    const client = new VoiceSocketClient({
      taskId: '111',
      sessionId: 'SESS-111',
      onStateChange: (state) => states.push(state),
    });

    await client.start();
    FakeWebSocket.instances[0]?.onerror?.();
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(stream.track.stop).toHaveBeenCalledOnce();
    expect(states.at(-1)).toBe('text_fallback');
  });

  it('无活动响应竞态不会关闭麦克风或切换文字降级', async () => {
    const stream = new FakeMediaStream();
    vi.stubGlobal('navigator', {
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue(stream),
      },
    });
    vi.stubGlobal('AudioContext', FakeAudioContext);
    vi.stubGlobal('WebSocket', FakeWebSocket);
    const states: string[] = [];
    const errors: string[] = [];
    const { VoiceSocketClient } = await import(
      '@/lib/transports/voiceSocket'
    );
    const client = new VoiceSocketClient({
      taskId: '111',
      sessionId: 'SESS-111',
      onStateChange: (state) => states.push(state),
      onError: (message) => errors.push(message),
    });

    await client.start();
    FakeWebSocket.instances[0]?.onmessage?.({
      data: JSON.stringify({
        type: 'error',
        code: 'invalid_request_error',
        message: 'Conversation has no active response.',
      }),
    });
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(stream.track.stop).not.toHaveBeenCalled();
    expect(errors).toEqual([]);
    expect(states.at(-1)).toBe('listening');
    await client.close();
  });
  it('上游失败给出具体提示，后续连接关闭不覆盖原始分类', async () => {
    const stream = new FakeMediaStream();
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia: vi.fn().mockResolvedValue(stream) } });
    vi.stubGlobal('AudioContext', FakeAudioContext);
    vi.stubGlobal('WebSocket', FakeWebSocket);
    const errors: string[] = [];
    const { VoiceSocketClient } = await import('@/lib/transports/voiceSocket');
    const client = new VoiceSocketClient({ taskId: '111', sessionId: 'SESS-111', onError: (message) => errors.push(message) });
    await client.start();
    FakeWebSocket.instances[0]?.onmessage?.({ data: JSON.stringify({ type: 'error', code: 'VOICE_UPSTREAM_FAILED', message: 'SECRET_PROVIDER_MESSAGE' }) });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(errors).toHaveLength(1);
    expect(errors[0]).toContain('语音模型');
    expect(errors[0]).toContain('VOICE_UPSTREAM_FAILED');
    expect(errors[0]).not.toContain('SECRET');
    await client.close();
  });

  it('暂停后迟到的后端监听状态不能伪装成麦克风已恢复', async () => {
    const stream = new FakeMediaStream();
    const getUserMedia = vi.fn().mockResolvedValueOnce(stream).mockResolvedValueOnce(new FakeMediaStream());
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } });
    vi.stubGlobal('AudioContext', FakeAudioContext);
    vi.stubGlobal('WebSocket', FakeWebSocket);
    const states: string[] = [];
    const { VoiceSocketClient } = await import('@/lib/transports/voiceSocket');
    const client = new VoiceSocketClient({ taskId: '111', sessionId: 'SESS-111', onStateChange: (s) => states.push(s) });
    await client.start();
    await client.pause();
    FakeWebSocket.instances[0]?.onmessage?.({ data: JSON.stringify({ type: 'state', state: 'listening' }) });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(client.isPaused).toBe(true);
    expect(states.at(-1)).toBe('paused');
    await client.resume();
    expect(client.isPaused).toBe(false);
    expect(getUserMedia).toHaveBeenCalledTimes(2);
    expect(states.at(-1)).toBe('listening');
    await client.close();
  });

  it('等待播报排空不能阻塞下一次说话事件，旧播报完成通知失效', async () => {
    const stream = new FakeMediaStream();
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia: vi.fn().mockResolvedValue(stream) } });
    vi.stubGlobal('AudioContext', FakeAudioContext);
    vi.stubGlobal('WebSocket', FakeWebSocket);
    const { Pcm16AudioPlayer } = await import('@/lib/audio/audioPlayer');
    let finish!: () => void;
    const pending = new Promise<void>((resolve) => { finish = resolve; });
    const wait = vi.spyOn(Pcm16AudioPlayer.prototype, 'waitForIdle').mockReturnValue(pending);
    const speech = vi.fn(); const completed = vi.fn();
    const { VoiceSocketClient } = await import('@/lib/transports/voiceSocket');
    const client = new VoiceSocketClient({ taskId: '111', sessionId: 'SESS-111', onSpeechStarted: speech, onPlaybackCompleted: completed });
    await client.start();
    const socket = FakeWebSocket.instances[0];
    try {
      socket?.onmessage?.({ data: JSON.stringify({ type: 'response_completed' }) });
      await new Promise((resolve) => setTimeout(resolve, 0));
      socket?.onmessage?.({ data: JSON.stringify({ type: 'speech_started' }) });
      await new Promise((resolve) => setTimeout(resolve, 0));
      expect(speech).toHaveBeenCalledOnce();
      finish();
      await new Promise((resolve) => setTimeout(resolve, 0));
      expect(completed).not.toHaveBeenCalled();
    } finally {
      finish(); wait.mockRestore(); await client.close();
    }
  });

  it('音轨意外结束只恢复一次，重复结束立即明确降级', async () => {
    const first = new FakeMediaStream(); const second = new FakeMediaStream();
    const getUserMedia = vi.fn().mockResolvedValueOnce(first).mockResolvedValueOnce(second);
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } });
    vi.stubGlobal('AudioContext', FakeAudioContext); vi.stubGlobal('WebSocket', FakeWebSocket);
    const errors: string[] = [];
    const { VoiceSocketClient } = await import('@/lib/transports/voiceSocket');
    const client = new VoiceSocketClient({ taskId: '111', sessionId: 'SESS-111', onError: (m) => errors.push(m) });
    await client.start(); first.track.endUnexpectedly();
    await new Promise((r) => setTimeout(r, 20));
    expect(getUserMedia).toHaveBeenCalledTimes(2); expect(errors).toEqual([]);
    second.track.endUnexpectedly(); await new Promise((r) => setTimeout(r, 20));
    expect(getUserMedia).toHaveBeenCalledTimes(2);
    expect(errors[0]).toContain('TrackEnded');
    await client.close();
  });
  it('主动暂停不自动重新申请麦克风', async () => {
    const stream = new FakeMediaStream(); const getUserMedia = vi.fn().mockResolvedValue(stream);
    vi.stubGlobal('navigator', { mediaDevices: { getUserMedia } });
    vi.stubGlobal('AudioContext', FakeAudioContext); vi.stubGlobal('WebSocket', FakeWebSocket);
    const { VoiceSocketClient } = await import('@/lib/transports/voiceSocket');
    const client = new VoiceSocketClient({ taskId: '111', sessionId: 'SESS-111' });
    await client.start(); await client.pause(); stream.track.endUnexpectedly();
    await new Promise((r) => setTimeout(r, 0));
    expect(getUserMedia).toHaveBeenCalledOnce(); await client.close();
  });

});
