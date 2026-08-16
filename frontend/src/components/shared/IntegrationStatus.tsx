import { Badge } from '@/components/shared/Badge';
import type { StreamConnectionStatus } from '@/lib/transports/sseClient';
import type { VoiceConnectionState } from '@/lib/transports/voiceSocket';
import { runtimeConfig } from '@/lib/runtime/config';

interface IntegrationStatusProps {
  streamStatus?: StreamConnectionStatus;
  voiceState?: VoiceConnectionState;
  compact?: boolean;
}

const streamLabels: Record<StreamConnectionStatus, string> = {
  idle: '未连接',
  connecting: 'SSE连接中',
  connected: 'SSE已连接',
  reconnecting: 'SSE重连中',
  closed: 'SSE已关闭',
  error: 'SSE异常',
};

const voiceLabels: Record<VoiceConnectionState, string> = {
  idle: '语音待机',
  connecting: '语音连接中',
  listening: '正在聆听',
  transcribing: '正在转录',
  thinking: 'AI思考中',
  speaking: 'AI播报中',
  paused: '语音已暂停',
  error: '语音异常',
  text_fallback: '已降级文字',
  closed: '语音已关闭',
};

export function IntegrationStatus({
  streamStatus,
  voiceState,
  compact = false,
}: IntegrationStatusProps) {
  const apiMode = runtimeConfig.dataMode === 'api';
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Badge variant={apiMode ? 'info' : 'default'} size="sm">
        {apiMode ? 'API联调' : 'Mock演示'}
      </Badge>
      {apiMode && streamStatus && (
        <Badge
          variant={streamStatus === 'connected' ? 'success' : 'warning'}
          size="sm"
        >
          {streamLabels[streamStatus]}
        </Badge>
      )}
      {!compact && apiMode && voiceState && (
        <Badge
          variant={
            voiceState === 'listening' || voiceState === 'speaking'
              ? 'success'
              : voiceState === 'text_fallback' || voiceState === 'error'
                ? 'warning'
                : 'default'
          }
          size="sm"
        >
          {voiceLabels[voiceState]}
        </Badge>
      )}
    </div>
  );
}
