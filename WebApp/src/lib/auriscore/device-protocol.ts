/** Physical/engineering publishers use v2; legacy simulator JSON v1 is unchanged. */
export const DEVICE_PROTOCOL = 2;
export const AUDIO_HEADER_BYTES = 32;
export const AUDIO_SAMPLES = 400;
export const AUDIO_FRAME_BYTES = AUDIO_HEADER_BYTES + AUDIO_SAMPLES * 2;
export interface DeviceHello { type: "device_hello"; protocol: 2; device: string; fw: string;
  source: "hardware" | "engineering"; streamId: number; samplingRate: 8000; channels: 1; encoding: "pcm16le" }
export interface AudioFrame { streamId: number; seq: number; firstSample: number; flags: number; samples: Int16Array }
const uint = (n: unknown, maximum = 0xffffffff): n is number => typeof n === "number" && Number.isInteger(n) && n >= 0 && n <= maximum;
export function parseDeviceHello(value: unknown): DeviceHello {
  const v = value as DeviceHello;
  if (!v || v.type !== "device_hello" || v.protocol !== 2 || typeof v.device !== "string" || !/^[\w-]{1,64}$/.test(v.device)
    || typeof v.fw !== "string" || v.fw.length < 1 || v.fw.length > 64
    || !["hardware", "engineering"].includes(v.source) || !uint(v.streamId) || !v.streamId
    || v.samplingRate !== 8000 || v.channels !== 1 || v.encoding !== "pcm16le") throw Error("Invalid device handshake");
  return v;
}
export function decodeAudioFrame(bytes: Uint8Array): AudioFrame {
  if (bytes.byteLength !== AUDIO_FRAME_BYTES) throw Error("Invalid audio frame length");
  const v = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (v.getUint32(0, false) !== 0x41555249 || v.getUint8(4) !== 2 || v.getUint16(6, true) !== 32
    || v.getUint32(24, true) !== 8000 || v.getUint16(28, true) !== 400 || v.getUint8(30) !== 1
    || v.getUint8(31) !== 1 || (v.getUint8(5) & ~1)) throw Error("Unsupported audio format");
  const firstSample = v.getUint32(16, true) + v.getUint32(20, true) * 0x100000000;
  if (!Number.isSafeInteger(firstSample) || !v.getUint32(8, true)) throw Error("Invalid sample clock");
  const samples = new Int16Array(400);
  for (let i = 0; i < 400; i++) samples[i] = v.getInt16(32 + i * 2, true);
  return { streamId: v.getUint32(8, true), seq: v.getUint32(12, true), firstSample, flags: v.getUint8(5), samples };
}
export function encodeAudioFrame(frame: AudioFrame): Uint8Array {
  if (!uint(frame.streamId) || !frame.streamId || !uint(frame.seq) || !uint(frame.flags, 1)
    || !Number.isSafeInteger(frame.firstSample) || frame.firstSample < 0 || frame.samples.length !== 400)
    throw Error("Invalid audio frame");
  const bytes = new Uint8Array(AUDIO_FRAME_BYTES), v = new DataView(bytes.buffer);
  v.setUint32(0, 0x41555249, false); v.setUint8(4, 2); v.setUint8(5, frame.flags); v.setUint16(6, 32, true);
  v.setUint32(8, frame.streamId, true); v.setUint32(12, frame.seq, true);
  v.setUint32(16, frame.firstSample % 0x100000000, true); v.setUint32(20, Math.floor(frame.firstSample / 0x100000000), true);
  v.setUint32(24, 8000, true); v.setUint16(28, 400, true); v.setUint8(30, 1); v.setUint8(31, 1);
  frame.samples.forEach((sample, i) => v.setInt16(32 + i * 2, sample, true)); return bytes;
}
/** TCP preserves ordering; duplicates are ignored, missing samples stop the stream. */
export class AudioContinuity {
  private last: AudioFrame | null = null;
  constructor(readonly streamId: number) {}
  accept(frame: AudioFrame): boolean {
    if (frame.streamId !== this.streamId || frame.flags) throw Error("Stream changed or acquisition overflow");
    if (this.last) {
      if (frame.seq === this.last.seq && frame.firstSample === this.last.firstSample) return false;
      if (frame.seq !== ((this.last.seq + 1) >>> 0) || frame.firstSample !== this.last.firstSample + 400)
        throw Error("Audio samples missing or out of order");
    }
    this.last = frame; return true;
  }
}
