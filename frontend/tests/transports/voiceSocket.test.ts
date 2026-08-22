import { afterEach, describe, expect, it, vi } from 'vitest';

class FakeTrack {
  stop = vi.fn();
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
  onclose: (() => void) | null = null;
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
    this.onclose?.();
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
});
