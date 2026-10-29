import { afterEach, describe, expect, it, vi } from 'vitest';
import { recordVoiceDiagnostic, VOICE_DIAGNOSTIC_KEY } from '@/lib/transports/voiceDiagnostics';

afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
describe('语音连接诊断', () => {
  it('有界保存连接信息，排除对话及密钥', () => {
    let stored = '[]';
    vi.stubGlobal('sessionStorage', { getItem: () => stored, setItem: (_key: string, value: string) => { stored = value; } });
    vi.spyOn(console, 'info').mockImplementation(() => {});
    for (let i = 0; i < 105; i++) recordVoiceDiagnostic('closed', { sessionId: 'SESS-TEST', code: 1006, message: 'SECRET_PATIENT', apiKey: 'SECRET_KEY' });
    expect(JSON.parse(stored)).toHaveLength(100);
    expect(stored).not.toContain('SECRET');
    expect(JSON.parse(stored)[0].code).toBe(1006);
    expect(VOICE_DIAGNOSTIC_KEY).toBe('medical:voice-diagnostics');
  });
  it('存储禁用时不影响语音', () => {
    vi.stubGlobal('sessionStorage', { getItem: () => { throw new Error('disabled'); } });
    vi.spyOn(console, 'info').mockImplementation(() => {});
    expect(() => recordVoiceDiagnostic('failed', { errorType: 'NotAllowedError' })).not.toThrow();
  });
});
