"use client";
import { useEffect, useState } from "react";
import { LiveListener } from "@/lib/auriscore/live-listener";
import type { PcgStream } from "@/hooks/use-pcg-stream";
export function LiveListening({ stream }: { stream: PcgStream }) {
  const [listener] = useState(() => new LiveListener());
  const [enabled, setEnabled] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState<string | null>(null);
  const { subscribePacket, subscribeConnection } = stream;
  useEffect(() => {
    const off = subscribePacket(packet => listener.accept(packet.samples));
    const offState = subscribeConnection(state => { if (state !== "connected") listener.reset(); });
    return () => { off(); offState(); void listener.stop(); };
  }, [listener, subscribePacket, subscribeConnection]);
  return <section aria-label="Dengarkan audio langsung">
    <button type="button" disabled={busy || (!enabled && !stream.isConnected)} onClick={async () => {
      setBusy(true); setError(null);
      try { if (enabled) await listener.stop(); else await listener.start(); setEnabled(!enabled); }
      catch { setError("Audio langsung memerlukan browser yang mendukung AudioWorklet dan HTTPS atau localhost."); }
      finally { setBusy(false); }
    }}>{enabled ? "Matikan suara langsung" : "Dengarkan langsung"}</button>
    <label> Volume <input type="range" min="0" max="1" step="0.05" defaultValue="0.5"
      disabled={!enabled} onChange={event => listener.volume(Number(event.target.value))} /></label>
    <p>Gunakan headphone untuk menghindari umpan balik. Suara langsung terpisah dari rekaman asli.</p>
    {error && <p role="alert">{error}</p>}
  </section>;
}
