"use client";

import { useState } from "react";
import { Cpu, Wifi, Link2, ShieldCheck, AlertCircle, ChevronDown, ChevronUp } from "lucide-react";

export interface StreamSettings {
  source: "mock" | "hardware";
  url: string;
  token: string;
}

export function DeviceConnect({
  disabled,
  onConnect,
}: {
  disabled: boolean;
  onConnect: (settings: StreamSettings) => void;
}) {
  const [source, setSource] = useState<"mock" | "hardware">("mock");
  const [url, setUrl] = useState("ws://localhost:8082/browser");
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="bg-white rounded-2xl border border-border/80 shadow-xs overflow-hidden transition-all">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          setError(null);
          if (source === "hardware") {
            try {
              const parsed = new URL(url);
              if (
                !["ws:", "wss:"].includes(parsed.protocol) ||
                parsed.pathname !== "/browser" ||
                parsed.username ||
                parsed.password ||
                parsed.search
              )
                throw Error();
              if (window.location.protocol === "https:" && parsed.protocol !== "wss:")
                throw Error();
            } catch {
              setError("Gunakan URL gateway /browser dengan ws:// atau wss:// yang sesuai.");
              return;
            }
            if (token.length < 16) {
              setError("Kode pairing minimal 16 karakter.");
              return;
            }
          }
          onConnect({ source, url, token });
        }}
        className="p-3.5 sm:p-4 space-y-3.5"
      >
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-emerald-50 border border-emerald-200/60 flex items-center justify-center text-emerald-700 flex-shrink-0">
              {source === "hardware" ? <Wifi className="w-4 h-4" /> : <Cpu className="w-4 h-4" />}
            </div>
            <div>
              <p className="text-xs font-semibold text-emerald-950 uppercase tracking-wider">
                Sumber Audio Masukan
              </p>
              <p className="text-xs text-muted-foreground">
                {source === "mock" ? "Simulator sintetis aktif" : "Perangkat keras ESP32"}
              </p>
            </div>
          </div>

          {/* Segmented Source Switcher */}
          <div className="grid grid-cols-2 p-1 bg-muted/60 rounded-xl border border-border/60 text-xs font-medium">
            <button
              type="button"
              disabled={disabled}
              onClick={() => {
                setSource("mock");
                setError(null);
              }}
              className={`flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg transition-all ${
                source === "mock"
                  ? "bg-white text-emerald-950 font-semibold shadow-xs"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Cpu className="w-3.5 h-3.5" />
              <span>Simulator</span>
            </button>
            <button
              type="button"
              disabled={disabled}
              onClick={() => {
                setSource("hardware");
                setIsExpanded(true);
                setError(null);
              }}
              className={`flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg transition-all ${
                source === "hardware"
                  ? "bg-white text-emerald-950 font-semibold shadow-xs"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Wifi className="w-3.5 h-3.5" />
              <span>ESP32 Wi-Fi</span>
            </button>
          </div>
        </div>

        {source === "hardware" && (
          <div className="space-y-3 pt-2 border-t border-border/50 text-xs">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                  <Link2 className="w-3 h-3 text-emerald-600" />
                  URL Gateway
                </label>
                <input
                  type="text"
                  value={url}
                  disabled={disabled}
                  onChange={(event) => setUrl(event.target.value)}
                  placeholder="ws://localhost:8082/browser"
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-foreground font-mono text-xs focus:outline-emerald-600 focus:ring-1 focus:ring-emerald-600 transition-all"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                  <ShieldCheck className="w-3 h-3 text-emerald-600" />
                  Kode Pairing (min 16 kar.)
                </label>
                <input
                  type="password"
                  autoComplete="off"
                  value={token}
                  disabled={disabled}
                  onChange={(event) => setToken(event.target.value)}
                  placeholder="Masukkan token pairing..."
                  className="w-full px-3 py-2 rounded-lg border border-border bg-background text-foreground font-mono text-xs focus:outline-emerald-600 focus:ring-1 focus:ring-emerald-600 transition-all"
                />
              </div>
            </div>
          </div>
        )}

        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2.5 pt-1">
          {error ? (
            <div role="alert" className="flex items-center gap-2 text-xs text-rose-700 bg-rose-50 px-3 py-2 rounded-lg border border-rose-200">
              <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
              <span>{error}</span>
            </div>
          ) : (
            <p className="text-[11.5px] text-muted-foreground">
              {source === "mock"
                ? "Simulasi sinyal PCG dengan laju sampling 8.000 Hz."
                : "Streaming langsung dari perangkat ESP32 melalui WebSocket."}
            </p>
          )}

          <button
            type="submit"
            disabled={disabled}
            className="flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-800 hover:bg-emerald-900 active:scale-[0.98] text-white text-xs font-semibold shadow-xs disabled:opacity-50 transition-all sm:self-end"
          >
            <span>Terapkan Sumber</span>
          </button>
        </div>
      </form>
    </div>
  );
}
