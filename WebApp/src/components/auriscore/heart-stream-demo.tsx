"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { HeartResultView } from "./heart-result-view";
import { HttpHeartAnalysisService } from "@/lib/auriscore/heart-analysis-service";
import { analyzeHeartAudio, PcgCaptureBuffer, type CaptureState } from "@/lib/auriscore/heart-audio-source";
import type { HeartAnalysisResult } from "@/lib/auriscore/heart-result";
import type { PcgStream } from "@/hooks/use-pcg-stream";

const service = new HttpHeartAnalysisService();
const CAPTURE_MS = 10_000;

/** Captures the existing validated mock/WebSocket PCM packets into the same Heart service as WAV. */
export function HeartStreamDemo({ stream, disabled = false }: { stream: PcgStream; disabled?: boolean }) {
  const [capture] = useState(() => new PcgCaptureBuffer());
  const [phase, setPhase] = useState<CaptureState>("idle");
  const [elapsedMs, setElapsedMs] = useState(0);
  const [result, setResult] = useState<HeartAnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [telemetry, setTelemetry] = useState(() => capture.telemetry());
  const [analysisInvoked, setAnalysisInvoked] = useState(false);
  const startedAt = useRef(0);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const inFlight = useRef(false);
  const { subscribePacket, subscribeConnection } = stream;

  const clearTimer = useCallback(() => {
    if (timer.current !== null) { clearInterval(timer.current); timer.current = null; }
  }, []);

  const stop = useCallback(async () => {
    if (inFlight.current || capture.state !== "recording") return;
    inFlight.current = true;
    clearTimer();
    setElapsedMs(Date.now() - startedAt.current);
    try {
      const audio = capture.stop(stream.isMock ? "mock" : "websocket-device");
      setTelemetry(capture.telemetry());
      setPhase("processing");
      setAnalysisInvoked(true);
      const analysis = await analyzeHeartAudio({ kind: "pcm", audio }, service);
      setResult(analysis);
      setPhase("completed");
    } catch (cause) {
      setResult(null);
      setError(`Audio/DSP: ${cause instanceof Error ? cause.message : String(cause)}`);
      setPhase("error");
    } finally {
      inFlight.current = false;
    }
  }, [capture, clearTimer, stream.isMock]);

  useEffect(() => {
    const offPacket = subscribePacket((packet) => {
      if (capture.state !== "recording") return;
      capture.accept(packet);
      if (capture.error !== null) {
        clearTimer();
        setTelemetry(capture.telemetry());
        setError(`Transport audio: ${capture.error}`);
        setPhase("error");
      }
    });
    const offConnection = subscribeConnection((state) => {
      if (state !== "disconnected" || capture.state !== "recording") return;
      capture.disconnect();
      clearTimer();
      setTelemetry(capture.telemetry());
      setError(`Koneksi: ${capture.error}`);
      setPhase("disconnected");
    });
    return () => { offPacket(); offConnection(); clearTimer(); };
  }, [capture, clearTimer, subscribePacket, subscribeConnection]);

  function start() {
    if (!stream.isConnected || disabled) { setError("Hubungkan sumber audio terlebih dahulu."); return; }
    capture.start();
    startedAt.current = Date.now();
    setResult(null);
    setError(null);
    setAnalysisInvoked(false);
    setElapsedMs(0);
    setTelemetry(capture.telemetry());
    setPhase("recording");
    clearTimer();
    timer.current = setInterval(() => {
      const elapsed = Date.now() - startedAt.current;
      setElapsedMs(elapsed);
      setTelemetry(capture.telemetry());
      if (elapsed >= CAPTURE_MS) void stop();
    }, 100);
  }

  return (
    <section className="auris-heart-demo" aria-labelledby="heart-stream-heading">
      <div className="auris-heart-demo-intro">
        <div><p className="auris-eyebrow">STREAM PCG · HEART DSP</p><h2 id="heart-stream-heading">Analisis rekaman perangkat</h2></div>
        <p>Jalur ini merekam paket PCM dari koneksi WebSocket yang ada, lalu menjalankan DSP Python yang sama dengan file WAV. Koneksi BLE fisik masih menunggu kontrak firmware.</p>
      </div>
      <p>Status: {phase} · {Math.min(elapsedMs / 1000, 10).toFixed(1)} / 10 detik</p>
      <button type="button" onClick={phase === "recording" ? () => void stop() : start}
        disabled={phase !== "recording" && (!stream.isConnected || disabled || phase === "processing")}>
        {phase === "recording" ? "Hentikan dan analisis Heart" : "Rekam dan analisis Heart"}
      </button>
      <div aria-live="polite">
        {phase === "processing" && <p role="status">DSP sedang memproses rekaman…</p>}
        {error && <p className="auris-heart-warning" role="alert">{error}</p>}
        {result && <HeartResultView result={result} />}
      </div>
      <details><summary>Telemetri pengembang</summary>
        <pre>{JSON.stringify({ connection: stream.state, uiPhase: phase, device: stream.hello?.device ?? null,
          analysisInvoked,
          analysisSucceeded: phase === "completed", ...telemetry }, null, 2)}</pre>
      </details>
      <p className="auris-heart-disclaimer">Keluaran skrining prototipe — bukan diagnosis. Sinyal simulator hanya uji rekayasa.</p>
    </section>
  );
}
