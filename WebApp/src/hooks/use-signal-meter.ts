"use client";
import { useEffect, useState } from "react";
import type { PcgStream } from "./use-pcg-stream";
import { SignalMeter, type SignalMetrics } from "@/lib/auriscore/signal-meter";

export function useSignalMeter(stream: PcgStream): SignalMetrics | null {
  const [metrics, setMetrics] = useState<SignalMetrics | null>(null);
  const { isConnected, subscribePacket, subscribeConnection } = stream;
  useEffect(() => {
    setMetrics(null);
    if (!isConnected) return;
    let meter = new SignalMeter();
    let latestPacketAt = -Infinity;
    const offPacket = subscribePacket(packet => {
      meter.accept(packet.samples);
      latestPacketAt = performance.now();
    });
    const offConnection = subscribeConnection(() => {
      meter = new SignalMeter(); latestPacketAt = -Infinity; setMetrics(null);
    });
    const timer = setInterval(() => {
      setMetrics(performance.now() - latestPacketAt > 2000 ? null : meter.read());
    }, 500);
    return () => { clearInterval(timer); offPacket(); offConnection(); };
  }, [isConnected, subscribePacket, subscribeConnection]);
  return isConnected ? metrics : null;
}
