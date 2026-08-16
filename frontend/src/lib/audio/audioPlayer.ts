export class Pcm16AudioPlayer {
  private context?: AudioContext;
  private nextStartTime = 0;
  private sources = new Set<AudioBufferSourceNode>();

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
    source.start(startAt);
    this.nextStartTime = startAt + audioBuffer.duration;
    this.sources.add(source);
    source.onended = () => this.sources.delete(source);
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
  }

  async close(): Promise<void> {
    this.interrupt();
    await this.context?.close();
    this.context = undefined;
  }
}
