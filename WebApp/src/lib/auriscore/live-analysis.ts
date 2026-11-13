import type { AnalysisMode } from "./analysis-result.ts";
import type { PcgPacketMsg } from "./protocol.ts";

export const LIVE_RATE = 8000;
export const LIVE_HOP_SAMPLES = LIVE_RATE;
// Outer context only. The Python backend still applies its frozen model windows.
export const LIVE_WINDOW_SAMPLES: Record<AnalysisMode, number> = {
  heart: 10 * LIVE_RATE, lung: 30 * LIVE_RATE, abdomen: 5 * LIVE_RATE,
};

export type LiveWindow = { pcm: ArrayBuffer; startSample: number; endSample: number };

/** Bounded PCM ring. Never interpolate or combine audio across discontinuities. */
export class LivePcmWindow {
  private readonly ring: Int16Array;
  private received = 0;
  private nextEnd: number;
  private previous: PcgPacketMsg | null = null;
  constructor(mode: AnalysisMode) {
    this.ring = new Int16Array(LIVE_WINDOW_SAMPLES[mode]);
    this.nextEnd = this.ring.length;
  }
  reset() {
    this.received = 0;
    this.previous = null;
    this.nextEnd = this.ring.length;
  }
  accept(packet: PcgPacketMsg): "ok" | "reset" {
    if (packet.samplingRate !== LIVE_RATE || packet.channels !== 1 || !packet.samples.length) {
      this.reset();
      return "reset";
    }
    const prior = this.previous;
    if (prior && packet.seq === prior.seq && packet.organMode === prior.organMode) return "ok";
    const gap = prior !== null && (packet.seq !== prior.seq + 1 || packet.organMode !== prior.organMode);
    if (gap) this.reset();
    for (const sample of packet.samples) this.ring[this.received++ % this.ring.length] = sample;
    this.previous = packet;
    return gap ? "reset" : "ok";
  }
  take(): LiveWindow | null {
    if (this.received < this.nextEnd) return null;
    const endSample = this.received;
    const startSample = endSample - this.ring.length;
    const pcm = new ArrayBuffer(this.ring.length * 2);
    const view = new DataView(pcm);
    for (let i = 0; i < this.ring.length; i++) view.setInt16(i * 2, this.ring[(startSample + i) % this.ring.length], true);
    this.nextEnd = endSample + LIVE_HOP_SAMPLES;
    return { pcm, startSample, endSample };
  }
}
