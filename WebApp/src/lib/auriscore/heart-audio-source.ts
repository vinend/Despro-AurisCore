/** Transport-independent PCM capture for Heart DSP. Physical BLE decoding stays explicit. */
import { parseServerMessage, type PcgPacketMsg } from "./protocol.ts";
import type { HeartAnalysisService } from "./heart-analysis-service.ts";

export type AudioSourceKind = "file" | "mock" | "ble" | "websocket-device";
export type CaptureState = "idle" | "connecting" | "connected" | "recording" | "processing" | "completed" | "error" | "disconnected";

export interface AnalysisReadyAudio {
  source: AudioSourceKind;
  waveform: Int16Array;
  sampleRate: number;
  packetsReceived: number;
  bytesReceived: number;
  missingPackets: number;
  durationSeconds: number;
  minimumSample: number;
  maximumSample: number;
}

const MAX_CAPTURE_SAMPLES = 8000 * 60;

/** Never fill sequence gaps with silence for analysis. Gaps fail the capture. */
export class PcgCaptureBuffer {
  state: CaptureState = "idle";
  private chunks: Int16Array[] = [];
  private lastSequence: number | null = null;
  private sampleRate: number | null = null;
  private sampleCount = 0;
  private packets = 0;
  private missing = 0;
  private min = 32767;
  private max = -32768;
  error: string | null = null;

  start(): void {
    this.chunks = [];
    this.lastSequence = null;
    this.sampleRate = null;
    this.sampleCount = 0;
    this.packets = 0;
    this.missing = 0;
    this.min = 32767;
    this.max = -32768;
    this.error = null;
    this.state = "recording";
  }

  accept(raw: unknown): void {
    if (this.state !== "recording") return;
    const message = parseServerMessage(raw);
    if (message?.type !== "pcg_packet") {
      this.fail("Paket PCG rusak atau tidak sesuai protokol.");
      return;
    }
    this.acceptPacket(message);
  }

  private acceptPacket(packet: PcgPacketMsg): void {
    if (this.sampleRate !== null && this.sampleRate !== packet.samplingRate) {
      this.fail("Laju sampling berubah saat rekaman.");
      return;
    }
    if (this.lastSequence !== null && packet.seq <= this.lastSequence) {
      // A delayed/duplicate packet is ignored; it must not duplicate samples.
      return;
    }
    if (this.lastSequence !== null && packet.seq > this.lastSequence + 1) {
      this.missing += packet.seq - this.lastSequence - 1;
      this.fail(`Paket audio hilang (${this.missing}); ulangi rekaman.`);
      return;
    }
    if (this.sampleCount + packet.samples.length > MAX_CAPTURE_SAMPLES) {
      this.fail("Rekaman melewati batas 60 detik.");
      return;
    }
    const chunk = Int16Array.from(packet.samples);
    for (const sample of chunk) {
      this.min = Math.min(this.min, sample);
      this.max = Math.max(this.max, sample);
    }
    this.chunks.push(chunk);
    this.sampleCount += chunk.length;
    this.sampleRate = packet.samplingRate;
    this.lastSequence = packet.seq;
    this.packets += 1;
  }

  disconnect(): void {
    if (this.state === "recording") this.fail("Koneksi terputus saat merekam.");
    else this.state = "disconnected";
  }

  private fail(reason: string): void {
    this.error = reason;
    this.state = "error";
  }

  telemetry() {
    return { state: this.state, packetsReceived: this.packets, bytesReceived: this.sampleCount * 2,
      missingPackets: this.missing, decodedSamples: this.sampleCount,
      sampleRate: this.sampleRate, durationSeconds: this.sampleRate ? this.sampleCount / this.sampleRate : 0,
      minimumSample: this.sampleCount ? this.min : null, maximumSample: this.sampleCount ? this.max : null,
      error: this.error };
  }

  stop(source: AudioSourceKind): AnalysisReadyAudio {
    if (this.state !== "recording" || !this.sampleRate || this.sampleCount === 0 || this.missing) {
      throw new Error(this.error ?? "Belum ada sampel audio yang dapat dianalisis.");
    }
    const waveform = new Int16Array(this.sampleCount);
    let offset = 0;
    for (const chunk of this.chunks) { waveform.set(chunk, offset); offset += chunk.length; }
    this.state = "processing";
    return { source, waveform, sampleRate: this.sampleRate, packetsReceived: this.packets,
      bytesReceived: this.sampleCount * 2, missingPackets: this.missing,
      durationSeconds: this.sampleCount / this.sampleRate,
      minimumSample: this.min, maximumSample: this.max };
  }
}

/** Encode the existing signed-PCM mock/device stream as a standard mono WAV. */
export function pcmToWavFile(audio: AnalysisReadyAudio): File {
  if (!Number.isInteger(audio.sampleRate) || audio.sampleRate <= 0 || audio.waveform.length === 0 ||
      audio.waveform.length * 2 + 44 > 16 * 1024 * 1024) {
    throw new Error("PCM Heart tidak valid atau terlalu besar.");
  }
  const buffer = new ArrayBuffer(44 + audio.waveform.length * 2);
  const view = new DataView(buffer);
  const ascii = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i));
  };
  ascii(0, "RIFF"); view.setUint32(4, buffer.byteLength - 8, true);
  ascii(8, "WAVE"); ascii(12, "fmt "); view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, audio.sampleRate, true); view.setUint32(28, audio.sampleRate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  ascii(36, "data"); view.setUint32(40, audio.waveform.length * 2, true);
  for (let i = 0; i < audio.waveform.length; i++) view.setInt16(44 + 2 * i, audio.waveform[i], true);
  return new File([buffer], "heart-capture.wav", { type: "audio/wav" });
}

export type HeartAudioInput = { kind: "file"; file: File } | { kind: "pcm"; audio: AnalysisReadyAudio };

export async function analyzeHeartAudio(input: HeartAudioInput, service: HeartAnalysisService) {
  return service.analyze(input.kind === "file" ? input.file : pcmToWavFile(input.audio));
}

/** Firmware-owned BLE transport and packet decoder must be supplied explicitly. */
export interface BleTransport {
  connect(onBytes: (packet: Uint8Array) => void, onDisconnect: () => void): Promise<void>;
  disconnect(): Promise<void>;
  startCapture(): Promise<void>;
  stopCapture(): Promise<void>;
}

export class BleAudioSource {
  state: CaptureState = "idle";
  readonly capture = new PcgCaptureBuffer();
  error: string | null = null;
  private readonly transport: BleTransport;
  private readonly decodePacket: (bytes: Uint8Array) => PcgPacketMsg;

  constructor(transport: BleTransport, decodePacket: (bytes: Uint8Array) => PcgPacketMsg) {
    this.transport = transport;
    this.decodePacket = decodePacket;
  }

  async connect(): Promise<void> {
    this.state = "connecting";
    try {
      await this.transport.connect(
        (bytes) => {
          try { this.capture.accept(this.decodePacket(bytes)); }
          catch { this.capture.accept(null); }
          if (this.capture.state === "error") { this.error = this.capture.error; this.state = "error"; }
        },
        () => { this.capture.disconnect(); this.state = "disconnected"; this.error = this.capture.error; },
      );
      this.state = "connected";
    } catch (error) { this.state = "error"; this.error = `BLE connect: ${String(error)}`; throw error; }
  }

  async startCapture(): Promise<void> {
    if (this.state !== "connected") throw new Error("BLE belum terhubung.");
    this.capture.start();
    try { await this.transport.startCapture(); this.state = "recording"; }
    catch (error) { this.capture.disconnect(); this.state = "error"; this.error = `BLE start: ${String(error)}`; throw error; }
  }

  async stopCapture(): Promise<AnalysisReadyAudio> {
    if (this.state !== "recording") throw new Error(this.error ?? "BLE tidak sedang merekam.");
    try { await this.transport.stopCapture(); }
    catch (error) { this.state = "error"; this.error = `BLE stop: ${String(error)}`; throw error; }
    const audio = this.capture.stop("ble");
    this.state = "processing";
    return audio;
  }

  async disconnect(): Promise<void> {
    await this.transport.disconnect();
    this.capture.disconnect();
    this.state = "disconnected";
  }
}
