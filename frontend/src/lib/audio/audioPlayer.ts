export class Pcm16AudioPlayer {
  private context?: AudioContext;
  private nextStartTime = 0;
  private sources = new Set<AudioBufferSourceNode>();
  private idleWaiters = new Set<() => void>();
  private activityVersion = 0;

  private ensureContext(): AudioContext {
    this.context ??= new AudioContext();
    return this.context;
  }

  async enqueue(buffer: ArrayBuffer, sampleRate = 24_000): Promise<void> {
    const context = this.ensureContext();
    if (context.state === 'suspended') await context.resume();
    const pcm = new Int16Array(buffer);
    const audioBuffer = context.createBuffer(1, pcm.length, sampleRate);
    const channel = audioBuffer.getChannelData(0);
    for (let index = 0; index < pcm.length; index += 1) {
      channel[index] = (pcm[index] ?? 0) / 32768;
    }
    const source = context.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(context.destination);
    const startAt = Math.max(context.currentTime, this.nextStartTime);
    source.onended = () => {
      this.sources.delete(source);
      this.notifyIdle();
    };
    this.activityVersion += 1;
    this.sources.add(source);
    source.start(startAt);
    this.nextStartTime = startAt + audioBuffer.duration;
  }

  private notifyIdle(): void {
    if (this.sources.size > 0) return;
    this.nextStartTime = this.context?.currentTime ?? 0;
    for (const resolve of this.idleWaiters) resolve();
    this.idleWaiters.clear();
  }

  private waitUntilSourcesEnd(): Promise<void> {
    if (this.sources.size === 0) return Promise.resolve();
    return new Promise((resolve) => this.idleWaiters.add(resolve));
  }

  async waitForIdle(quietWindowMs = 300): Promise<void> {
    while (true) {
      await this.waitUntilSourcesEnd();
      const quietVersion = this.activityVersion;
      if (quietWindowMs > 0) {
        await new Promise((resolve) => setTimeout(resolve, quietWindowMs));
      }
      if (this.sources.size === 0 && this.activityVersion === quietVersion) {
        return;
      }
    }
  }

  interrupt(): void {
    for (const source of this.sources) {
      try {
        source.stop();
      } catch {
        // 已结束的节点无需重复停止。
      }
    }
    this.sources.clear();
    this.nextStartTime = this.context?.currentTime ?? 0;
    this.notifyIdle();
  }

  async close(): Promise<void> {
    this.interrupt();
    await this.context?.close();
    this.context = undefined;
  }
}
