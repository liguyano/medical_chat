import { measurePcm16, type VoiceCaptureDiagnostics } from '@/lib/audio/voiceCaptureStats';
import { describeVoiceFailure, type VoiceFailureStage } from '@/lib/patient/voiceFailure';
import { recordVoiceDiagnostic } from './voiceDiagnostics';

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
  onDiagnostics?: (data: VoiceCaptureDiagnostics) => void;
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
  private acquisitionVersion = 0;
  private removeTrackListeners: Array<() => void> = [];

  async start(onFrame: (frame: ArrayBuffer) => void, onEnded?: () => void): Promise<void> {
    const version = ++this.acquisitionVersion;
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    if (version !== this.acquisitionVersion) {
      for (const track of stream.getTracks()) track.stop();
      return;
    }
    this.stream = stream;
    for (const track of stream.getTracks()) {
      if (track.readyState === 'ended') throw Object.assign(new Error('音轨已结束'), { name: 'TrackEnded' });
      const ended = () => {
        if (version !== this.acquisitionVersion) return;
        if (this.processor) this.processor.onaudioprocess = null;
        onEnded?.();
      };
      track.addEventListener?.('ended', ended);
      this.removeTrackListeners.push(() => track.removeEventListener?.('ended', ended));
    }
    this.context = new AudioContext();
    await this.context.resume();
    if (version !== this.acquisitionVersion) return;
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

  diagnostics() {
    const track = this.stream?.getTracks().find((item) => item.kind === 'audio') ?? this.stream?.getTracks()[0];
    return { device: track?.label || '默认输入设备', trackState: track?.readyState ?? '未开启',
      muted: track?.muted ?? false, enabled: track?.enabled ?? false,
      contextState: this.context?.state ?? '未开启', sampleRate: this.context?.sampleRate ?? 0 };
  }

  async stop(): Promise<void> {
    this.acquisitionVersion += 1;
    for (const remove of this.removeTrackListeners) remove();
    this.removeTrackListeners = [];
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
  private readonly diagnosticConnectionId = `browser-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  private diagnose(event: string, metadata: Record<string, string | number | boolean | undefined> = {}) {
    recordVoiceDiagnostic(event, { sessionId: this.options.sessionId,
      connectionId: this.diagnosticConnectionId, state: this.state,
      readyState: this.socket?.readyState, ...metadata });
  }
  private failureReported = false;
  private reportFailure(stage: VoiceFailureStage, code?: string): string {
    const detail = describeVoiceFailure(stage, code);
    if (!this.failureReported) {
      this.failureReported = true;
      this.options.onError?.(detail);
    }
    return detail;
  }
  private socket?: WebSocket;
  private capture = new MicrophonePcmCapture();
  private player = new Pcm16AudioPlayer();
  private state: VoiceConnectionState = 'idle';
  private capturePaused = false;
  get isPaused(): boolean { return this.capturePaused; }
  private closingPromise?: Promise<void>;
  private intentionalClose = false;
  private responsePending = false;
  private playbackCompletionVersion = 0;
  private responseWaiters = new Set<() => void>();
  private messageChain: Promise<void> = Promise.resolve();

  constructor(private readonly options: VoiceSocketOptions) {}

  private trackRecoveryAttempts = 0;
  private trackRecoveryInFlight = false;
  private handleTrackEnded = () => {
    if (this.intentionalClose || this.capturePaused || this.trackRecoveryInFlight) return;
    this.diagnose('microphone_track_ended');
    this.publishDiagnostics();
    if (this.trackRecoveryAttempts >= 1) {
      this.reportFailure('microphone', 'TrackEnded');
      void this.cleanupAfterUnexpectedClose();
      return;
    }
    this.trackRecoveryAttempts += 1;
    this.trackRecoveryInFlight = true;
    this.setState('connecting');
    void (async () => {
      try {
        await this.capture.stop();
        if (this.intentionalClose || this.capturePaused) return;
        await this.capture.start(this.forwardFrame, this.handleTrackEnded);
        if (this.intentionalClose || this.capturePaused) return;
        if (this.capture.diagnostics().trackState === 'ended') {
          throw Object.assign(new Error('音轨恢复后已结束'), { name: 'TrackEnded' });
        }
        this.diagnose('microphone_track_recovered');
        this.publishDiagnostics();
        this.setState('listening');
      } catch (error) {
        if (this.intentionalClose || this.capturePaused) return;
        this.diagnose('microphone_recovery_failed', { errorType: error instanceof Error ? error.name : 'unknown' });
        this.reportFailure('microphone', error instanceof Error ? error.name : 'TrackEnded');
        await this.cleanupAfterUnexpectedClose();
      } finally {
        this.trackRecoveryInFlight = false;
      }
    })();
  };
  private diagnosticTimer?: ReturnType<typeof setInterval>;
  private captureFrames = 0;
  private sentAudioBytes = 0;
  private lastCaptureAt = 0;
  private energy = { rms: 0, peak: 0 };
  private publishDiagnostics = () => {
    this.options.onDiagnostics?.({ ...this.capture.diagnostics(), ...this.energy,
      frames: this.captureFrames, sentBytes: this.sentAudioBytes, lastFrameAt: this.lastCaptureAt,
      socketState: this.socket?.readyState ?? 3 });
  };
  private forwardFrame = (frame: ArrayBuffer) => {
    this.captureFrames += 1;
    this.lastCaptureAt = Date.now();
    this.energy = measurePcm16(frame);
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(frame);
      this.sentAudioBytes += frame.byteLength;
    }
  };

  private setState(state: VoiceConnectionState) {
    if (this.capturePaused && (state === 'listening' || state === 'transcribing')) state = 'paused';
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
    this.failureReported = false;
    if (!navigator.mediaDevices?.getUserMedia) {
      this.setState('text_fallback');
      throw new Error(this.reportFailure('unsupported'));
    }
    this.diagnose('connect_start');
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
        this.socket.onopen = () => { this.diagnose('transport_open'); resolve(); };
        this.socket.onerror = () => reject(new Error('语音连接失败'));
      });
    } catch (error) {
      this.diagnose('connect_failed', { errorType: error instanceof Error ? error.name : 'unknown' });
      this.reportFailure('connect');
      this.socket?.close();
      this.setState('text_fallback');
      throw error;
    }

    this.socket.onmessage = (event) => {
      this.messageChain = this.messageChain
        .then(() => this.handleMessage(event.data))
        .catch((error) => {
          this.diagnose('message_failed', { errorType: error instanceof Error ? error.name : 'unknown' });
          this.reportFailure('message', error instanceof Error ? error.name : 'UNKNOWN');
          this.setState('text_fallback');
        });
    };
    this.socket.onclose = (event) => {
      this.diagnose('transport_closed', { code: event.code, wasClean: event.wasClean });
      if (this.intentionalClose || this.state === 'closed') return;
      this.reportFailure('closed', String(event.code));
      void this.cleanupAfterUnexpectedClose();
    };
    this.socket.onerror = () => {
      this.diagnose('transport_error');
      this.reportFailure('network');
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
      await this.capture.start(this.forwardFrame, this.handleTrackEnded);
      if (this.intentionalClose) return;
      this.capturePaused = false;
      this.diagnosticTimer = setInterval(this.publishDiagnostics, 500);
      this.publishDiagnostics();
      this.setState('listening');
    } catch (error) {
      this.diagnose('microphone_failed', { errorType: error instanceof Error ? error.name : 'unknown' });
      this.setState('text_fallback');
      this.reportFailure('microphone', error instanceof Error ? error.name : 'UNKNOWN');
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
      this.playbackCompletionVersion += 1;
      this.options.onSpeechStarted?.();
      this.player.interrupt();
      this.completePendingResponse();
      this.setState('listening');
    } else if (message.type === 'speech_stopped') {
      this.setState('transcribing');
    } else if (message.type === 'interrupted') {
      this.playbackCompletionVersion += 1;
      this.player.interrupt();
      this.completePendingResponse();
      this.setState('listening');
    } else if (message.type === 'response_completed') {
      this.completePendingResponse();
      const version = ++this.playbackCompletionVersion;
      // 播放等待不得阻塞WebSocket控制消息；新说话/关闭使迟到通知失效。
      void this.player.waitForIdle().then(() => {
        if (version === this.playbackCompletionVersion && !this.intentionalClose) {
          this.options.onPlaybackCompleted?.();
        }
      }).catch((error) => {
        if (version !== this.playbackCompletionVersion || this.intentionalClose) return;
        this.diagnose('playback_failed', { errorType: error instanceof Error ? error.name : 'unknown' });
        this.reportFailure('message', error instanceof Error ? error.name : 'UNKNOWN');
        void this.cleanupAfterUnexpectedClose();
      });
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
      this.diagnose('server_error', { code: message.code });
      this.completePendingResponse();
      this.reportFailure('server', message.code);
      await this.cleanupAfterUnexpectedClose();
    } else if (message.type === 'closed') {
      this.completePendingResponse();
      await this.finishLocalClose({ waitForPlayback: true, notifyServer: false });
    }
  }

  private async cleanupAfterUnexpectedClose(): Promise<void> {
    if (this.diagnosticTimer) clearInterval(this.diagnosticTimer);
    this.playbackCompletionVersion += 1;
    this.diagnose('text_fallback');
    this.intentionalClose = true;
    this.completePendingResponse();
    await this.capture.stop();
    this.player.interrupt();
    this.socket?.close();
    this.socket = undefined;
    await this.player.close();
    this.publishDiagnostics();
    this.setState('text_fallback');
  }

  private finishLocalClose(options: {
    waitForPlayback: boolean;
    notifyServer: boolean;
  }): Promise<void> {
    this.closingPromise ??= (async () => {
      if (this.diagnosticTimer) clearInterval(this.diagnosticTimer);
      this.playbackCompletionVersion += 1;
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
      this.publishDiagnostics();
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
    this.playbackCompletionVersion += 1;
    this.player.interrupt();
    this.sendControl({ type: 'interrupt' });
    this.setState('listening');
  }

  async pause(): Promise<void> {
    this.capturePaused = true;
    this.diagnose('microphone_paused');
    await this.capture.stop();
    this.sendControl({ type: 'pause' });
    this.setState('paused');
  }

  async resume(): Promise<void> {
    try {
      await this.capture.start(this.forwardFrame, this.handleTrackEnded);
    } catch (error) {
      this.reportFailure('microphone', error instanceof Error ? error.name : 'UNKNOWN');
      this.setState('text_fallback');
      throw error;
    }
    if (this.intentionalClose) return;
    this.capturePaused = false;
    this.diagnose('microphone_resumed');
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
