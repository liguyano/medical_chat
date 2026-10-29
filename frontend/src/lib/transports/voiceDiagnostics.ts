export const VOICE_DIAGNOSTIC_KEY = 'medical:voice-diagnostics';

/** 只保留连接元数据；禁止传入对话、音频、URL、凭据和原始错误消息。 */
export function recordVoiceDiagnostic(
  event: string,
  metadata: Record<string, string | number | boolean | undefined>
): void {
  const allowed = new Set(['sessionId', 'connectionId', 'state', 'readyState', 'code', 'wasClean', 'errorType']);
  const entry: Record<string, unknown> = { time: new Date().toISOString(), event };
  for (const [key, value] of Object.entries(metadata)) {
    if (!allowed.has(key) || value === undefined) continue;
    entry[key] = typeof value === 'string'
      ? (/^[A-Za-z0-9_.:/-]{1,128}$/.test(value) ? value : 'redacted')
      : value;
  }
  try {
    const previous: unknown = JSON.parse(sessionStorage.getItem(VOICE_DIAGNOSTIC_KEY) ?? '[]');
    const entries = Array.isArray(previous) ? previous : [];
    sessionStorage.setItem(VOICE_DIAGNOSTIC_KEY, JSON.stringify([...entries.slice(-99), entry]));
  } catch {
    // 日志不可用不能中断语音。
  }
  console.info('[voice-diagnostic]', entry);
}
