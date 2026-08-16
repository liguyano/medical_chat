import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiRequest } from '@/lib/api/httpClient';

describe('HTTP client', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('携带Cookie并解析JSON响应', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
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
        new Response(JSON.stringify({ detail: '任务不存在', code: 'NOT_FOUND' }), {
          status: 404,
          headers: { 'Content-Type': 'application/json' },
        })
      )
    );
    await expect(apiRequest('/api/missing')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      code: 'NOT_FOUND',
      message: '任务不存在',
    } satisfies Partial<ApiError>);
  });
});
