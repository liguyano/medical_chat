'use client';

import { useEffect, useMemo, useSyncExternalStore } from 'react';
import { createQuestionProgressResource } from '@/lib/dialogue/questionProgress';
import { careRepository } from '@/lib/repositories';

export function useQuestionProgress(sessionId: string | undefined, refreshKey: string) {
  const resource = useMemo(
    () => createQuestionProgressResource(careRepository, sessionId), [sessionId]
  );
  const state = useSyncExternalStore(resource.subscribe, resource.getSnapshot, resource.getSnapshot);
  useEffect(() => {
    if (!sessionId) return;
    const interval = window.setInterval(() => { void resource.refresh(true); }, 15000);
    return () => {
      window.clearInterval(interval);
      resource.cancel();
    };
  }, [resource, sessionId]);
  useEffect(() => { void resource.refresh(); }, [resource, refreshKey]);
  return { ...state, refresh: resource.refresh };
}
