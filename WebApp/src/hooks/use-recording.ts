"use client";
import { useEffect, useState, useSyncExternalStore } from "react";
import type { PcgStream } from "./use-pcg-stream";
import type { AnalysisMode } from "@/lib/auriscore/analysis-result";
import { HttpOrganAnalysisService } from "@/lib/auriscore/organ-analysis-service";
import { RecordingSession, recordingDurationMs } from "@/lib/auriscore/recording-session";
export { RECORD_DURATION_MS } from "@/lib/auriscore/recording-session";
export type { RecordingPhase, HistoryEntry } from "@/lib/auriscore/recording-session";
const service = new HttpOrganAnalysisService();
export function useRecording(stream: PcgStream, mode: AnalysisMode) {
  const [session] = useState(() => new RecordingSession(service));
  const snapshot = useSyncExternalStore(session.subscribe, session.getSnapshot, session.getSnapshot);
  const { subscribePacket, subscribeConnection } = stream;
  useEffect(() => {
    const offPacket = subscribePacket(packet => session.accept(packet));
    const offConnection = subscribeConnection(state => { if (state !== "connected") session.disconnect(); });
    return () => { offPacket(); offConnection(); session.dispose(); };
  }, [session, subscribePacket, subscribeConnection]);
  return { ...snapshot, durationMs: recordingDurationMs(mode), start: () => { if (stream.isConnected) session.start(mode, stream.isMock ? "mock" : "websocket-device"); },
    stop: () => { void session.stop(); }, reset: () => session.reset() };
}
