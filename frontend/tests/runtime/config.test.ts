import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  createRuntimeConfig,
  toWebSocketUrl,
} from '@/lib/runtime/config';

describe('runtime config', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('默认使用Mock模式，避免后端未完成时阻断原型', () => {
    vi.stubEnv('NEXT_PUBLIC_DATA_MODE', '');
    vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', '');
    const config = createRuntimeConfig();
    expect(config.dataMode).toBe('mock');
    expect(config.dialogTransport).toBe('websocket');
  });

  it('规范化API地址并转换WebSocket协议', () => {
    const config = createRuntimeConfig({
      dataMode: 'api',
      apiBaseUrl: 'https://medical.example.com/',
    });
    expect(config.apiBaseUrl).toBe('https://medical.example.com');
    expect(toWebSocketUrl(config.apiBaseUrl)).toBe(
      'wss://medical.example.com'
    );
  });
});
