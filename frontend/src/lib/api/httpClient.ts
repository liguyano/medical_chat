import { runtimeConfig } from '@/lib/runtime/config';
import type { ApiResponse } from '@/lib/api/contracts';

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

export function isRequestCancelled(error: unknown): boolean {
  return (
    (error instanceof ApiError &&
      error.status === 0 &&
      error.message === '请求已取消') ||
    (error instanceof DOMException && error.name === 'AbortError') ||
    (error instanceof Error && error.name === 'AbortError')
  );
}

export function abortRequest(controller: AbortController): void {
  if (!controller.signal.aborted) {
    // 使用浏览器标准 AbortError，避免把组件卸载原因作为异常字符串暴露给
    // Chrome inspector 等调试扩展，同时仍由 apiRequest 统一转换成静默取消。
    controller.abort();
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
    const responseBody =
      payload && typeof payload === 'object'
        ? (payload as Partial<ApiResponse<unknown>> &
            Record<string, unknown>)
        : undefined;
    if (!response.ok) {
      throw new ApiError(
        String(
          responseBody?.message ??
            responseBody?.detail ??
            `请求失败（HTTP ${response.status}）`
        ),
        response.status,
        typeof responseBody?.code === 'string'
          ? responseBody.code
          : undefined,
        payload
      );
    }
    if (
      responseBody &&
      typeof responseBody.code === 'string' &&
      'data' in responseBody
    ) {
      if (responseBody.code !== 'OK') {
        throw new ApiError(
          String(responseBody.message ?? '请求失败'),
          response.status,
          responseBody.code,
          payload
        );
      }
      return responseBody.data as T;
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
