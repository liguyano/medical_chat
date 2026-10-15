import { abortRequest } from '@/lib/api/httpClient';

interface DialogueSnapshotLoadOptions<T> {
  load: (signal: AbortSignal) => Promise<T>;
  onSuccess: (snapshot: T) => void;
  onError: (error: unknown) => void;
}

export function startDialogueSnapshotLoad<T>({
  load,
  onSuccess,
  onError,
}: DialogueSnapshotLoadOptions<T>): () => void {
  const controller = new AbortController();
  void load(controller.signal)
    .then((snapshot) => {
      if (!controller.signal.aborted) onSuccess(snapshot);
    })
    .catch((error: unknown) => {
      if (!controller.signal.aborted) onError(error);
    });
  return () => abortRequest(controller);
}
