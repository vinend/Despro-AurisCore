"use client";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";
import type { PcgStream } from "./use-pcg-stream";
import type { AnalysisMode } from "@/lib/auriscore/analysis-result";
import { HttpOrganAnalysisService } from "@/lib/auriscore/organ-analysis-service";
import { RecordingSession, recordingDurationMs } from "@/lib/auriscore/recording-session";
import { CLOUD_AUDIO_STALL_MS, LAN_AUDIO_STALL_MS } from "@/lib/auriscore/stream-timing";
export { RECORD_DURATION_MS } from "@/lib/auriscore/recording-session";
export type { RecordingPhase, HistoryEntry } from "@/lib/auriscore/recording-session";
export function useRecording(stream: PcgStream, mode: AnalysisMode) {
  const stallMs = process.env.NEXT_PUBLIC_AURISCORE_CLOUD === "1" ? CLOUD_AUDIO_STALL_MS : LAN_AUDIO_STALL_MS;
  const [session] = useState(() => new RecordingSession(new HttpOrganAnalysisService(), stallMs));
  const snapshot = useSyncExternalStore(session.subscribe, session.getSnapshot, session.getSnapshot);
  const clear = useCallback(() => session.clearHistory(), [session]);
  const { subscribePacket, subscribeConnection } = stream;
  useEffect(() => {
    const offPacket = subscribePacket(packet => session.accept(packet));
    const offConnection = subscribeConnection(state => { if (state !== "connected") session.disconnect(); });
    return () => { offPacket(); offConnection(); session.dispose(); };
  }, [session, subscribePacket, subscribeConnection]);
  return { ...snapshot, clear, durationMs: recordingDurationMs(mode), start: () => { if (stream.isConnected) session.start(mode, stream.isMock ? "mock" : "websocket-device"); },
    stop: () => { void session.stop(); }, reset: () => session.reset() };
}
