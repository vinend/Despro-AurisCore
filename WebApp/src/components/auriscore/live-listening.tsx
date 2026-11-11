"use client";

import { useEffect, useState } from "react";
import { Headphones, Volume2, VolumeX, AlertCircle, Radio } from "lucide-react";
import { LiveListener } from "@/lib/auriscore/live-listener";
import type { PcgStream } from "@/hooks/use-pcg-stream";

export function LiveListening({ stream }: { stream: PcgStream }) {
  const [listener] = useState(() => new LiveListener());
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [volumeVal, setVolumeVal] = useState(0.5);
  const [error, setError] = useState<string | null>(null);
  const { subscribePacket, subscribeConnection } = stream;

  useEffect(() => {
    const off = subscribePacket((packet) => listener.accept(packet.samples));
    const offState = subscribeConnection((state) => {
      if (state !== "connected") listener.reset();
    });
    return () => {
      off();
      offState();
      void listener.stop();
    };
  }, [listener, subscribePacket, subscribeConnection]);

  return (
    <section
      aria-label="Dengarkan audio langsung"
      className="p-4 sm:p-5 border-b border-border/60 bg-muted/20"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <div className={`w-7 h-7 rounded-lg flex items-center justify-center transition-colors ${
            enabled ? "bg-emerald-600 text-white" : "bg-muted text-muted-foreground"
          }`}>
            <Headphones className="w-3.5 h-3.5" />
          </div>
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-emerald-950">
              Audio Langsung
            </h3>
            <p className="text-[11px] text-muted-foreground">
              {enabled ? "Memonitor audio secara real-time" : "AudioWorklet lokal"}
            </p>
          </div>
        </div>

        {enabled && (
          <span className="flex items-center gap-1.5 text-[11px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
            <Radio className="w-3 h-3 text-emerald-600 animate-pulse" />
            Aktif
          </span>
        )}
      </div>

      <div className="space-y-3">
        <button
          type="button"
          disabled={busy || (!enabled && !stream.isConnected)}
          onClick={async () => {
            setBusy(true);
            setError(null);
            try {
              if (enabled) {
                await listener.stop();
              } else {
                await listener.start();
              }
              setEnabled(!enabled);
            } catch {
              setError(
                "Audio langsung memerlukan browser yang mendukung AudioWorklet dan HTTPS atau localhost."
              );
            } finally {
              setBusy(false);
            }
          }}
          className={`w-full min-h-[42px] px-3 py-2 rounded-xl text-xs font-semibold flex items-center justify-center gap-2 transition-all active:scale-[0.98] ${
            enabled
              ? "bg-rose-50 text-rose-700 hover:bg-rose-100 border border-rose-200"
              : "bg-white text-emerald-950 hover:bg-emerald-50 border border-border/80 shadow-xs"
          } disabled:opacity-50`}
        >
          <Headphones className="w-3.5 h-3.5" />
          <span>{enabled ? "Matikan Suara Langsung" : "Dengarkan Langsung (Headphone)"}</span>
        </button>

        <div className="flex items-center gap-3 pt-1">
          {volumeVal === 0 ? (
            <VolumeX className="w-4 h-4 text-muted-foreground flex-shrink-0" />
          ) : (
            <Volume2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
          )}
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={volumeVal}
            disabled={!enabled}
            onChange={(event) => {
              const val = Number(event.target.value);
              setVolumeVal(val);
              listener.volume(val);
            }}
            aria-label="Volume audio langsung"
            className="w-full accent-emerald-600 h-1.5 bg-muted rounded-lg cursor-pointer disabled:opacity-40"
          />
          <span className="text-[11px] font-mono text-muted-foreground w-8 text-right">
            {Math.round(volumeVal * 100)}%
          </span>
        </div>

        <p className="text-[11px] text-muted-foreground leading-relaxed">
          Gunakan headphone untuk menghindari umpan balik akustik. Suara langsung terpisah dari rekaman asli.
        </p>

        {error && (
          <div role="alert" className="flex items-start gap-2 p-2.5 rounded-lg bg-rose-50 text-rose-700 text-xs border border-rose-200">
            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}
      </div>
    </section>
  );
}
