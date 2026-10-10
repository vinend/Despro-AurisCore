/** Real PCM recording lifecycle, independent of React and simulator classification. */
import { PcgCaptureBuffer, pcmToWavFile, type AudioSourceKind } from "./heart-audio-source.ts";
import type { AnalysisMode, OrganAnalysisResult } from "./analysis-result.ts";
import type { OrganAnalysisService } from "./organ-analysis-service.ts";
export type RecordingPhase = "idle" | "recording" | "processing" | "done" | "error";
export const RECORD_DURATION_MS = 10_000;
export interface HistoryEntry { id: number; ts: number; mode: AnalysisMode; source: AudioSourceKind;
  durationMs: number; result: OrganAnalysisResult }
export interface RecordingSnapshot { phase: RecordingPhase; elapsedMs: number; error: string | null;
  result: OrganAnalysisResult | null; history: HistoryEntry[]; file: File | null }
export class RecordingSession {
  private capture = new PcgCaptureBuffer();
  private listeners = new Set<() => void>();
  private snapshot: RecordingSnapshot = { phase: "idle", elapsedMs: 0, error: null, result: null, history: [], file: null };
  private timer: ReturnType<typeof setInterval> | null = null;
  private abort: AbortController | null = null;
  private generation = 0;
  private mode: AnalysisMode = "heart";
  private source: AudioSourceKind = "websocket-device";
  private started = 0;
  private sequence = 0;
  private receivedSamples = 0;
  private lastPacketAt = 0;
  constructor(private readonly service: OrganAnalysisService) {}
  getSnapshot = () => this.snapshot;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private update(patch: Partial<RecordingSnapshot>) {
    this.snapshot = { ...this.snapshot, ...patch };
    for (const listener of this.listeners) listener();
  }
  private clearTimer() { if (this.timer) clearInterval(this.timer); this.timer = null; }
  start(mode: AnalysisMode, source: AudioSourceKind) {
    if (["recording", "processing"].includes(this.snapshot.phase)) return;
    this.generation++;
    this.mode = mode; this.source = source; this.started = Date.now();
    this.capture.start(); this.receivedSamples = 0; this.lastPacketAt = Date.now();
    this.update({ phase: "recording", elapsedMs: 0, error: null, result: null, file: null });
    this.timer = setInterval(() => {
      this.update({ elapsedMs: this.receivedSamples / 8 });
      if (Date.now() - this.lastPacketAt > 2000 || Date.now() - this.started > 15_000) {
        this.disconnect();
      }
    }, 100);
  }
  accept(packet: unknown) {
    if (this.snapshot.phase !== "recording") return;
    this.capture.accept(packet);
    if (this.capture.error) { this.clearTimer(); this.update({ phase: "error", error: this.capture.error }); return; }
    this.receivedSamples = this.capture.telemetry().decodedSamples; this.lastPacketAt = Date.now();
    if (this.receivedSamples >= 80_000) void this.stop();
  }
  disconnect() {
    if (this.snapshot.phase !== "recording") return;
    this.capture.disconnect(); this.clearTimer();
    this.update({ phase: "error", error: this.capture.error ?? "Sumber audio terputus. Ulangi rekaman." });
  }
  async stop() {
    if (this.snapshot.phase !== "recording") return;
    this.clearTimer();
    const generation = this.generation;
    try {
      const audio = this.capture.stop(this.source);
      const file = pcmToWavFile(audio);
      this.abort = new AbortController();
      this.update({ phase: "processing", elapsedMs: audio.durationSeconds * 1000, file });
      const result = await this.service.analyze(file, this.mode, this.abort.signal);
      if (generation !== this.generation) return;
      this.sequence++;
      const entry = { id: this.sequence, ts: Date.now(), mode: this.mode, source: this.source,
        durationMs: audio.durationSeconds * 1000, result };
      this.update({ phase: "done", result, history: [entry, ...this.snapshot.history].slice(0, 50) });
    } catch (error) {
      if (generation === this.generation) this.update({ phase: "error", result: null,
        error: error instanceof Error ? error.message : "Analisis rekaman gagal." });
    } finally { if (generation === this.generation) this.abort = null; }
  }
  reset() {
    this.generation++; this.clearTimer(); this.abort?.abort(); this.abort = null;
    this.update({ phase: "idle", elapsedMs: 0, error: null, result: null, file: null });
  }
  dispose() { this.reset(); }
}
