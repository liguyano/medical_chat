export const PCM16_MIN = -32768;
export const PCM16_MAX = 32767;

export function float32ToPcm16(samples: Float32Array): Int16Array {
  const output = new Int16Array(samples.length);
  for (let index = 0; index < samples.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, samples[index] ?? 0));
    output[index] =
      sample < 0
        ? Math.round(sample * -PCM16_MIN)
        : Math.round(sample * PCM16_MAX);
  }
  return output;
}

export function downsampleFloat32(
  samples: Float32Array,
  inputSampleRate: number,
  outputSampleRate = 16_000
): Float32Array {
  if (outputSampleRate > inputSampleRate) {
    throw new Error('输出采样率不能高于输入采样率');
  }
  if (outputSampleRate === inputSampleRate) return samples.slice();
  const ratio = inputSampleRate / outputSampleRate;
  const outputLength = Math.max(1, Math.round(samples.length / ratio));
  const output = new Float32Array(outputLength);
  let inputOffset = 0;
  for (let outputOffset = 0; outputOffset < outputLength; outputOffset += 1) {
    const nextInputOffset = Math.min(
      samples.length,
      Math.round((outputOffset + 1) * ratio)
    );
    let total = 0;
    let count = 0;
    for (
      let index = inputOffset;
      index < nextInputOffset;
      index += 1
    ) {
      total += samples[index] ?? 0;
      count += 1;
    }
    output[outputOffset] = count ? total / count : 0;
    inputOffset = nextInputOffset;
  }
  return output;
}

export function encodePcm16Frame(
  samples: Float32Array,
  inputSampleRate: number,
  outputSampleRate = 16_000
): ArrayBuffer {
  const downsampled = downsampleFloat32(
    samples,
    inputSampleRate,
    outputSampleRate
  );
  const pcm = float32ToPcm16(downsampled);
  const buffer = new ArrayBuffer(pcm.byteLength);
  new Int16Array(buffer).set(pcm);
  return buffer;
}

export function decodeBase64ToArrayBuffer(value: string): ArrayBuffer {
  const binary = globalThis.atob(value);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes.buffer;
}
