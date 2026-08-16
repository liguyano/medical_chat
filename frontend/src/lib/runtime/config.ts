export type DataMode = 'mock' | 'api';
export type DialogTransport = 'websocket';

export interface RuntimeConfig {
  dataMode: DataMode;
  apiBaseUrl: string;
  dialogTransport: DialogTransport;
  requestTimeoutMs: number;
}

const DEFAULT_API_BASE_URL = 'http://localhost:8000';
const DEFAULT_REQUEST_TIMEOUT_MS = 15_000;

function normalizeBaseUrl(value: string): string {
  return value.replace(/\/+$/, '');
}

function parseDataMode(value: string | undefined): DataMode {
  return value?.toLowerCase() === 'api' ? 'api' : 'mock';
}

function parsePositiveInteger(value: string | undefined, fallback: number): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

export function createRuntimeConfig(
  overrides: Partial<RuntimeConfig> = {}
): RuntimeConfig {
  return {
    dataMode:
      overrides.dataMode ??
      parseDataMode(process.env.NEXT_PUBLIC_DATA_MODE),
    apiBaseUrl: normalizeBaseUrl(
      overrides.apiBaseUrl ??
        process.env.NEXT_PUBLIC_API_BASE_URL ??
        DEFAULT_API_BASE_URL
    ),
    dialogTransport: 'websocket',
    requestTimeoutMs:
      overrides.requestTimeoutMs ??
      parsePositiveInteger(
        process.env.NEXT_PUBLIC_API_TIMEOUT_MS,
        DEFAULT_REQUEST_TIMEOUT_MS
      ),
  };
}

export const runtimeConfig = createRuntimeConfig();

export function toWebSocketUrl(baseUrl: string): string {
  const url = new URL(baseUrl);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return normalizeBaseUrl(url.toString());
}
