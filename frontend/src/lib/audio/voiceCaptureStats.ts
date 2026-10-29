export interface VoiceCaptureDiagnostics {
  device: string; trackState: string; muted: boolean; enabled: boolean;
  contextState: string; sampleRate: number; rms: number; peak: number;
  frames: number; sentBytes: number; lastFrameAt: number; socketState: number;
}
export function measurePcm16(frame: ArrayBuffer): { rms: number; peak: number } {
  const values = new Int16Array(frame); let sum = 0; let peak = 0;
  for (const value of values) { sum += value * value; peak = Math.max(peak, Math.abs(value)); }
  return { rms: values.length ? Math.round(Math.sqrt(sum / values.length)) : 0, peak };
}
