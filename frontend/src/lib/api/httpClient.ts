import { runtimeConfig } from '@/lib/runtime/config';

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
    public readonly details?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  timeoutMs?: number;
}

function mergeAbortSignals(
  controller: AbortController,
  externalSignal?: AbortSignal | null
): () => void {
  if (!externalSignal) return () => undefined;
  if (externalSignal.aborted) {
    controller.abort(externalSignal.reason);
    return () => undefined;
  }
  const abort = () => controller.abort(externalSignal.reason);
  externalSignal.addEventListener('abort', abort, { once: true });
  return () => externalSignal.removeEventListener('abort', abort);
}

async function parseResponseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined;
  const contentType = response.headers.get('content-type') ?? '';
  if (contentType.includes('application/json')) return response.json();
  const text = await response.text();
  return text || undefined;
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const controller = new AbortController();
  const cleanupExternalSignal = mergeAbortSignals(controller, options.signal);
  const timeout = globalThis.setTimeout(
    () => controller.abort(new DOMException('请求超时', 'TimeoutError')),
    options.timeoutMs ?? runtimeConfig.requestTimeoutMs
  );

  try {
    const response = await fetch(`${runtimeConfig.apiBaseUrl}${path}`, {
      ...options,
      body:
        options.body === undefined
          ? undefined
          : JSON.stringify(options.body),
      credentials: 'include',
      headers: {
        Accept: 'application/json',
        ...(options.body === undefined
          ? {}
          : { 'Content-Type': 'application/json' }),
        ...options.headers,
      },
      signal: controller.signal,
    });
    const payload = await parseResponseBody(response);
    if (!response.ok) {
      const errorPayload =
        payload && typeof payload === 'object'
          ? (payload as Record<string, unknown>)
          : undefined;
      throw new ApiError(
        String(
          errorPayload?.message ??
            errorPayload?.detail ??
            `请求失败（HTTP ${response.status}）`
        ),
        response.status,
        typeof errorPayload?.code === 'string'
          ? errorPayload.code
          : undefined,
        payload
      );
    }
    return payload as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (controller.signal.aborted) {
      const reason = controller.signal.reason;
      const timedOut =
        reason instanceof DOMException && reason.name === 'TimeoutError';
      throw new ApiError(timedOut ? '请求超时，请稍后重试' : '请求已取消', 0);
    }
    throw new ApiError(
      error instanceof Error ? error.message : '网络请求失败',
      0
    );
  } finally {
    globalThis.clearTimeout(timeout);
    cleanupExternalSignal();
  }
}
