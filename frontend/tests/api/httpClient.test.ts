import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  ApiError,
  abortRequest,
  apiRequest,
  isRequestCancelled,
} from '@/lib/api/httpClient';

describe('HTTP client', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('携带Cookie并解析JSON响应', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        code: 'OK',
        message: '成功',
        data: { ok: true },
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    );
    vi.stubGlobal('fetch', fetchMock);
    await expect(apiRequest<{ ok: boolean }>('/api/test')).resolves.toEqual({
      ok: true,
    });
    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/api/test',
      expect.objectContaining({ credentials: 'include' })
    );
  });

  it('将后端错误转换为可观察ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({
          code: 'ERR_TASK_003',
          message: '任务不存在',
          data: null,
        }), {
          status: 404,
          headers: { 'Content-Type': 'application/json' },
        })
      )
    );
    await expect(apiRequest('/api/missing')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      code: 'ERR_TASK_003',
      message: '任务不存在',
    } satisfies Partial<ApiError>);
  });

  it('主动取消请求时可被页面静默识别', () => {
    const controller = new AbortController();
    abortRequest(controller);

    expect(controller.signal.aborted).toBe(true);
    expect(
      isRequestCancelled(new ApiError('请求已取消', 0))
    ).toBe(true);
    expect(isRequestCancelled(new Error('网络错误'))).toBe(false);
  });
});
