import type {
  VoiceClientMessage,
  VoiceServerMessage,
} from '@/lib/api/contracts';
import { Pcm16AudioPlayer } from '@/lib/audio/audioPlayer';
import {
  decodeBase64ToArrayBuffer,
  encodePcm16Frame,
} from '@/lib/audio/pcm16';
import { runtimeConfig, toWebSocketUrl } from '@/lib/runtime/config';

export type VoiceConnectionState =
  | 'idle'
  | 'connecting'
  | 'listening'
  | 'transcribing'
  | 'thinking'
  | 'speaking'
  | 'paused'
  | 'error'
  | 'text_fallback'
  | 'closed';

export interface VoiceSocketOptions {
  taskId: string;
  sessionId: string;
  onStateChange?: (state: VoiceConnectionState) => void;
  onError?: (message: string) => void;
}

class MicrophonePcmCapture {
  private stream?: MediaStream;
  private context?: AudioContext;
  private processor?: ScriptProcessorNode;
  private source?: MediaStreamAudioSourceNode;

  async start(onFrame: (frame: ArrayBuffer) => void): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    this.context = new AudioContext();
    await this.context.resume();
    this.source = this.context.createMediaStreamSource(this.stream);
    this.processor = this.context.createScriptProcessor(4096, 1, 1);
    const inputSampleRate = this.context.sampleRate;
    this.processor.onaudioprocess = (event) => {
      const samples = event.inputBuffer.getChannelData(0);
      onFrame(encodePcm16Frame(samples, inputSampleRate));
    };
    this.source.connect(this.processor);
    this.processor.connect(this.context.destination);
  }

  async stop(): Promise<void> {
    if (this.processor) {
      this.processor.onaudioprocess = null;
      this.processor.disconnect();
    }
    this.source?.disconnect();
    for (const track of this.stream?.getTracks() ?? []) track.stop();
    await this.context?.close();
    this.processor = undefined;
    this.source = undefined;
    this.stream = undefined;
    this.context = undefined;
  }
}

export class VoiceSocketClient {
  private socket?: WebSocket;
  private capture = new MicrophonePcmCapture();
  private player = new Pcm16AudioPlayer();
  private state: VoiceConnectionState = 'idle';

  constructor(private readonly options: VoiceSocketOptions) {}

  private setState(state: VoiceConnectionState) {
    this.state = state;
    this.options.onStateChange?.(state);
  }

  private sendControl(message: VoiceClientMessage): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(message));
    }
  }

  async start(): Promise<void> {
    if (this.state !== 'idle' && this.state !== 'closed') return;
    if (!navigator.mediaDevices?.getUserMedia) {
      this.setState('text_fallback');
      throw new Error('当前浏览器不支持麦克风采集');
    }
    this.setState('connecting');
    const base = toWebSocketUrl(runtimeConfig.apiBaseUrl);
    const url = `${base}/api/ws/dialog/${encodeURIComponent(
      this.options.sessionId
    )}/voice`;
    this.socket = new WebSocket(url);
    this.socket.binaryType = 'arraybuffer';

    await new Promise<void>((resolve, reject) => {
      if (!this.socket) return reject(new Error('语音连接创建失败'));
      this.socket.onopen = () => resolve();
      this.socket.onerror = () => reject(new Error('语音连接失败'));
    });

    this.socket.onmessage = (event) => {
      void this.handleMessage(event.data);
    };
    this.socket.onclose = () => {
      if (this.state !== 'closed') this.setState('text_fallback');
    };
    this.socket.onerror = () => {
      this.options.onError?.('语音网络异常，已切换为文字输入');
      this.setState('text_fallback');
    };

    this.sendControl({
      type: 'start',
      task_id: this.options.taskId,
      session_id: this.options.sessionId,
      format: 'pcm_s16le',
      sample_rate: 16000,
      channels: 1,
    });
    try {
      await this.capture.start((frame) => {
        if (this.socket?.readyState === WebSocket.OPEN) {
          this.socket.send(frame);
        }
      });
      this.setState('listening');
    } catch (error) {
      this.setState('text_fallback');
      this.options.onError?.(
        error instanceof Error ? error.message : '无法访问麦克风'
      );
      this.socket.close();
      throw error;
    }
  }

  private async handleMessage(data: string | ArrayBuffer | Blob) {
    if (data instanceof ArrayBuffer) {
      this.setState('speaking');
      await this.player.enqueue(data);
      return;
    }
    if (data instanceof Blob) {
      this.setState('speaking');
      await this.player.enqueue(await data.arrayBuffer());
      return;
    }
    const message = JSON.parse(data) as VoiceServerMessage;
    if (message.type === 'state') {
      this.setState(message.state);
    } else if (message.type === 'audio') {
      this.setState('speaking');
      await this.player.enqueue(
        decodeBase64ToArrayBuffer(message.audio_base64),
        message.sample_rate
      );
    } else if (message.type === 'error') {
      this.options.onError?.(message.message);
      this.setState('text_fallback');
    } else if (message.type === 'closed') {
      this.setState('closed');
    }
  }

  async commit(): Promise<void> {
    await this.capture.stop();
    this.sendControl({ type: 'commit' });
    this.setState('transcribing');
  }

  interrupt(): void {
    this.player.interrupt();
    this.sendControl({ type: 'interrupt' });
    this.setState('listening');
  }

  pause(): void {
    this.sendControl({ type: 'pause' });
    this.setState('paused');
  }

  resume(): void {
    this.sendControl({ type: 'resume' });
    this.setState('listening');
  }

  async close(): Promise<void> {
    await this.capture.stop();
    this.player.interrupt();
    this.sendControl({ type: 'close' });
    this.socket?.close();
    await this.player.close();
    this.setState('closed');
  }
}
