"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  fakeClassify,
  type ClassificationResult,
} from "@/lib/auriscore/fake-classifier";
import type { OrganMode } from "@/lib/auriscore/protocol";

/** Durasi rekaman otomatis: 10 detik (seksi 9). */
export const RECORD_DURATION_MS = 10_000;
/** Durasi status "memproses" tiruan: 1,5 detik (seksi 9). */
const PROCESSING_DELAY_MS = 1_500;

export type RecordingPhase = "idle" | "recording" | "processing" | "done";

export interface HistoryEntry extends ClassificationResult {
  id: number;
}

export interface RecordingApi {
  phase: RecordingPhase;
  elapsedMs: number;
  result: ClassificationResult | null;
  history: HistoryEntry[];
  /** Mulai merekam (10 dtk, berhenti otomatis). */
  start: (organMode: OrganMode) => void;
  /** Berhenti lebih awal → tetap diproses dengan durasi aktual. */
  stop: () => void;
}

/**
 * Alur rekaman (seksi 9): Rekam berjalan maksimal 10 detik → berhenti otomatis
 * → status "memproses" 1,5 detik → kartu hasil klasifikasi tiruan + entri
 * riwayat dalam memori.
 */
export function useRecording(): RecordingApi {
  const [phase, setPhase] = useState<RecordingPhase>("idle");
  const [elapsedMs, setElapsedMs] = useState(0);
  const [result, setResult] = useState<ClassificationResult | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);

  const phaseRef = useRef<RecordingPhase>("idle");
  const startRef = useRef(0);
  const modeAtStartRef = useRef<OrganMode>("mitral");
  const idRef = useRef(0);
  const tickTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const processTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimers = useCallback(() => {
    if (tickTimerRef.current !== null) {
      clearInterval(tickTimerRef.current);
      tickTimerRef.current = null;
    }
    if (processTimerRef.current !== null) {
      clearTimeout(processTimerRef.current);
      processTimerRef.current = null;
    }
  }, []);

  // Berhenti merekam (manual atau otomatis penuh 10 dtk) → status "memproses".
  const finish = useCallback(() => {
    if (phaseRef.current !== "recording") return;
    clearTimers();
    const duration = Math.min(Date.now() - startRef.current, RECORD_DURATION_MS);
    setElapsedMs(duration);
    phaseRef.current = "processing";
    setPhase("processing");
    processTimerRef.current = setTimeout(() => {
      processTimerRef.current = null;
      const res = fakeClassify(modeAtStartRef.current, duration);
      setResult(res);
      idRef.current += 1;
      setHistory((prev) => [{ ...res, id: idRef.current }, ...prev]);
      phaseRef.current = "done";
      setPhase("done");
    }, PROCESSING_DELAY_MS);
  }, [clearTimers]);

  const start = useCallback(
    (organMode: OrganMode) => {
      if (phaseRef.current === "recording" || phaseRef.current === "processing") {
        return;
      }
      clearTimers();
      modeAtStartRef.current = organMode;
      setResult(null);
      setElapsedMs(0);
      startRef.current = Date.now();
      phaseRef.current = "recording";
      setPhase("recording");
      tickTimerRef.current = setInterval(() => {
        const elapsed = Date.now() - startRef.current;
        if (elapsed >= RECORD_DURATION_MS) {
          finish(); // berhenti otomatis pada 10 detik
        } else {
          setElapsedMs(elapsed);
        }
      }, 100);
    },
    [clearTimers, finish]
  );

  // Bersihkan semua timer saat komponen dilepas.
  useEffect(() => clearTimers, [clearTimers]);

  return { phase, elapsedMs, result, history, start, stop: finish };
}
