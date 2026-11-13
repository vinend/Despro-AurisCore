"use client";
import { useEffect, useRef, useState } from "react";
import type { PcgStream } from "./use-pcg-stream";
import { parseOrganAnalysisResult, type AnalysisMode, type OrganAnalysisResult } from "@/lib/auriscore/analysis-result";
import { LivePcmWindow } from "@/lib/auriscore/live-analysis";

type LiveResult = { result: OrganAnalysisResult; startSample: number; endSample: number; elapsedMs: number };
export function useLiveAnalysis(stream: PcgStream, mode: AnalysisMode, enabled: boolean) {
  const [latest, setLatest] = useState<LiveResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  const { subscribePacket, subscribeConnection, isConnected } = stream;
  useEffect(() => {
    setLatest(null);
    setError(null);
    if (!enabled || !isConnected) return;
    const window = new LivePcmWindow(mode);
    let generation = 0;
    let disposed = false;
    let lastPacket = performance.now();
    let stalled = false;
    const reset = () => {
      generation++;
      window.reset();
      setLatest(null);
      setError(null);
    };
    const offConnection = subscribeConnection(() => reset());
    const offPacket = subscribePacket(packet => {
      const now = performance.now();
      if (now - lastPacket > 2000 && !stalled) reset();
      lastPacket = now;
      stalled = false;
      if (window.accept(packet) === "reset") {
        generation++;
        setLatest(null);
        setError(null);
      }
      if (inFlight.current) return;
      const next = window.take();
      if (!next) return;
      const version = generation;
      inFlight.current = true;
      void (async () => {
        try {
          const response = await fetch(`/api/analysis/live?mode=${mode}`, {
            method: "POST", headers: { "Content-Type": "application/octet-stream",
              "X-AurisCore-Start-Sample": String(next.startSample) }, body: next.pcm,
          });
          if (response.status === 429) return; // Shared worker is busy; don't queue stale audio.
          if (!response.ok) throw new Error("Analisis langsung belum tersedia.");
          const payload = await response.json();
          if (payload.startSample !== next.startSample || payload.endSample !== next.endSample)
            throw new Error("Respons jendela audio tidak sesuai.");
          const result = parseOrganAnalysisResult(payload.result, mode);
          if (!disposed && version === generation) {
            setLatest({ result, startSample: next.startSample, endSample: next.endSample,
              elapsedMs: Math.round(performance.now() - now) });
            setError(null);
          }
        } catch {
          if (!disposed && version === generation) {
            setLatest(null);
            setError("Analisis langsung belum tersedia. Periksa backend dan paket model.");
          }
        } finally { inFlight.current = false; }
      })();
    });
    const watchdog = setInterval(() => {
      if (!stalled && performance.now() - lastPacket > 2000) {
        stalled = true;
        reset();
      }
    }, 250);
    return () => {
      disposed = true;
      clearInterval(watchdog);
      offPacket();
      offConnection();
    };
  }, [mode, enabled, isConnected, subscribePacket, subscribeConnection]);
  return { latest: enabled && isConnected && latest?.result.mode === mode ? latest : null, error };
}
