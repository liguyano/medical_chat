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
  onTranscriptReady?: (transcript: {
    transcriptId: string;
    text: string;
    turnNo: number;
    messageId?: string;
    audioUrl?: string | null;
  }) => void;
  onTranscriptConfirmed?: (transcriptId: string) => void;
  onTranscriptDiscarded?: (transcriptId: string) => void;
  onSpeechStarted?: () => void;
  onPlaybackCompleted?: () => void;
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
    const processor = this.processor;
    const source = this.source;
    const stream = this.stream;
    const context = this.context;
    this.processor = undefined;
    this.source = undefined;
    this.stream = undefined;
    this.context = undefined;
    if (processor) {
      processor.onaudioprocess = null;
      processor.disconnect();
    }
    source?.disconnect();
    for (const track of stream?.getTracks() ?? []) track.stop();
    await context?.close();
  }
}

export class VoiceSocketClient {
  private socket?: WebSocket;
  private capture = new MicrophonePcmCapture();
  private player = new Pcm16AudioPlayer();
  private state: VoiceConnectionState = 'idle';
  private closingPromise?: Promise<void>;
  private intentionalClose = false;
  private responsePending = false;
  private responseWaiters = new Set<() => void>();
  private messageChain: Promise<void> = Promise.resolve();

  constructor(private readonly options: VoiceSocketOptions) {}

  private forwardFrame = (frame: ArrayBuffer) => {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(frame);
    }
  };

  private setState(state: VoiceConnectionState) {
    this.state = state;
    if (state === 'thinking' || state === 'speaking') {
      this.responsePending = true;
    }
    this.options.onStateChange?.(state);
  }

  private completePendingResponse(): void {
    this.responsePending = false;
    for (const resolve of this.responseWaiters) resolve();
    this.responseWaiters.clear();
  }

  private waitForPendingResponse(): Promise<void> {
    if (!this.responsePending) return Promise.resolve();
    return new Promise((resolve) => this.responseWaiters.add(resolve));
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

    try {
      await new Promise<void>((resolve, reject) => {
        if (!this.socket) return reject(new Error('语音连接创建失败'));
        this.socket.onopen = () => resolve();
        this.socket.onerror = () => reject(new Error('语音连接失败'));
      });
    } catch (error) {
      this.socket?.close();
      this.setState('text_fallback');
      throw error;
    }

    this.socket.onmessage = (event) => {
      this.messageChain = this.messageChain
        .then(() => this.handleMessage(event.data))
        .catch((error) => {
          this.options.onError?.(
            error instanceof Error ? error.message : '语音消息处理失败'
          );
          this.setState('text_fallback');
        });
    };
    this.socket.onclose = () => {
      if (this.intentionalClose || this.state === 'closed') return;
      void this.cleanupAfterUnexpectedClose();
    };
    this.socket.onerror = () => {
      this.options.onError?.('语音网络异常，已切换为文字输入');
      void this.cleanupAfterUnexpectedClose();
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
      await this.capture.start(this.forwardFrame);
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
    } else if (message.type === 'speech_started') {
      this.options.onSpeechStarted?.();
      this.player.interrupt();
      this.completePendingResponse();
      this.setState('listening');
    } else if (message.type === 'speech_stopped') {
      this.setState('transcribing');
    } else if (message.type === 'interrupted') {
      this.player.interrupt();
      this.completePendingResponse();
      this.setState('listening');
    } else if (message.type === 'response_completed') {
      this.completePendingResponse();
      await this.player.waitForIdle();
      this.options.onPlaybackCompleted?.();
    } else if (message.type === 'audio') {
      this.setState('speaking');
      await this.player.enqueue(
        decodeBase64ToArrayBuffer(message.audio_base64),
        message.sample_rate
      );
    } else if (message.type === 'transcript_ready') {
      this.options.onTranscriptReady?.({
        transcriptId: message.transcript_id,
        text: message.text,
        turnNo: message.turn_no,
        messageId: message.message_id,
        audioUrl: message.audio_url,
      });
      this.setState('transcribing');
    } else if (message.type === 'transcript_confirmed') {
      this.options.onTranscriptConfirmed?.(message.transcript_id);
      this.setState('thinking');
    } else if (message.type === 'transcript_discarded') {
      this.options.onTranscriptDiscarded?.(message.transcript_id);
      this.setState('listening');
    } else if (
      message.type === 'error' &&
      /conversation has no active response/i.test(message.message)
    ) {
      // 上游取消/重复触发响应的竞态不应关闭麦克风或降级文字输入。
      this.completePendingResponse();
      this.setState('listening');
    } else if (message.type === 'error') {
      this.completePendingResponse();
      this.options.onError?.(message.message);
      await this.cleanupAfterUnexpectedClose();
    } else if (message.type === 'closed') {
      this.completePendingResponse();
      await this.finishLocalClose({ waitForPlayback: true, notifyServer: false });
    }
  }

  private async cleanupAfterUnexpectedClose(): Promise<void> {
    this.intentionalClose = true;
    this.completePendingResponse();
    await this.capture.stop();
    this.player.interrupt();
    this.socket?.close();
    this.socket = undefined;
    await this.player.close();
    this.setState('text_fallback');
  }

  private finishLocalClose(options: {
    waitForPlayback: boolean;
    notifyServer: boolean;
  }): Promise<void> {
    this.closingPromise ??= (async () => {
      this.intentionalClose = true;
      await this.capture.stop();
      if (options.waitForPlayback) {
        await this.waitForPendingResponse();
        await this.player.waitForIdle();
      } else {
        this.completePendingResponse();
        this.player.interrupt();
      }
      if (options.notifyServer) this.sendControl({ type: 'close' });
      this.socket?.close();
      this.socket = undefined;
      await this.player.close();
      this.setState('closed');
    })();
    return this.closingPromise;
  }

  async commit(): Promise<void> {
    await this.capture.stop();
    this.sendControl({ type: 'commit' });
    this.setState('transcribing');
  }

  confirmTranscript(transcriptId: string): void {
    this.sendControl({ type: 'confirm_transcript', transcript_id: transcriptId });
  }

  retryTranscript(transcriptId: string): void {
    this.sendControl({ type: 'retry_transcript', transcript_id: transcriptId });
  }

  interrupt(): void {
    this.player.interrupt();
    this.sendControl({ type: 'interrupt' });
    this.setState('listening');
  }

  async pause(): Promise<void> {
    await this.capture.stop();
    this.sendControl({ type: 'pause' });
    this.setState('paused');
  }

  async resume(): Promise<void> {
    try {
      await this.capture.start(this.forwardFrame);
    } catch (error) {
      this.options.onError?.(
        error instanceof Error ? error.message : '无法恢复麦克风采集'
      );
      this.setState('text_fallback');
      throw error;
    }
    this.sendControl({ type: 'resume' });
    this.setState('listening');
  }

  async close(): Promise<void> {
    await this.finishLocalClose({
      waitForPlayback: false,
      notifyServer: true,
    });
  }

  async finishAndCloseAfterPlayback(): Promise<void> {
    await this.finishLocalClose({
      waitForPlayback: true,
      notifyServer: true,
    });
  }
}
