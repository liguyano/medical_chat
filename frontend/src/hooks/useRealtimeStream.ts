'use client';

import { useEffect, useState } from 'react';
import { applyRealtimeEvent } from '@/lib/transports/applyRealtimeEvent';
import {
  SseClient,
  type StreamConnectionStatus,
} from '@/lib/transports/sseClient';
import { runtimeConfig } from '@/lib/runtime/config';

interface UseRealtimeStreamOptions {
  path?: string;
  enabled?: boolean;
}

export function useRealtimeStream({
  path,
  enabled = true,
}: UseRealtimeStreamOptions): {
  status: StreamConnectionStatus;
  error: string;
} {
  const [status, setStatus] = useState<StreamConnectionStatus>('idle');
  const [error, setError] = useState('');

  useEffect(() => {
    if (
      !enabled ||
      runtimeConfig.dataMode !== 'api' ||
      !path
    ) {
      return;
    }
    const client = new SseClient({
      path,
      onEvent: applyRealtimeEvent,
      onStatusChange: setStatus,
      onError: (streamError) => setError(streamError.message),
    });
    client.connect();
    return () => client.close();
  }, [enabled, path]);

  return {
    status:
      enabled && runtimeConfig.dataMode === 'api' && path
        ? status
        : 'idle',
    error,
  };
}
