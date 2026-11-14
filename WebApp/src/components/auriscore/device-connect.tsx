"use client";

import { useEffect, useState } from "react";
import { Wifi, Link2, ShieldCheck, AlertCircle } from "lucide-react";
import { defaultGatewayUrl } from "@/lib/auriscore/gateway-url";

export interface StreamSettings {
  source: "mock" | "hardware";
  url: string;
  token: string;
}

/** Physical-device controls; simulator adapters remain in engineering tooling. */
export function DeviceConnect({ disabled, connected, onConnect, onDisconnect }: {
  disabled: boolean;
  connected: boolean;
  onConnect: (settings: StreamSettings) => void;
  onDisconnect: () => void;
}) {
  const [url, setUrl] = useState("");
  const [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { setUrl(defaultGatewayUrl(window.location)); }, []);

  return (
    <section aria-label="Koneksi ESP32" className="min-w-0 bg-white rounded-2xl border border-border/80 shadow-xs overflow-hidden">
      <form className="p-3.5 sm:p-4 space-y-3.5" onSubmit={event => {
        event.preventDefault();
        if (disabled) return;
        setError(null);
        const gateway = url.trim();
        try {
          const parsed = new URL(gateway);
          if (!["ws:", "wss:"].includes(parsed.protocol) || parsed.pathname !== "/browser"
            || parsed.username || parsed.password || parsed.search || parsed.hash
            || (window.location.protocol === "https:" && parsed.protocol !== "wss:")) throw Error();
        } catch {
          setError("Gunakan URL gateway /browser dengan ws:// atau wss:// yang sesuai.");
          return;
        }
        if (token.trim().length < 16) {
          setError("Kode pairing minimal 16 karakter.");
          return;
        }
        onConnect({ source: "hardware", url: gateway, token: token.trim() });
      }}>
        <div className="flex items-center gap-2.5">
          <Wifi className="w-5 h-5 text-emerald-700 shrink-0" />
          <div>
            <h2 className="text-xs font-semibold text-emerald-950 uppercase tracking-wider">Perangkat ESP32</h2>
            <p className="text-xs text-muted-foreground">Audio alat melalui gateway laptop · HP dan laptop pada Wi-Fi yang sama.</p>
          </div>
        </div>
        <div className="grid min-w-0 gap-3 sm:grid-cols-2">
          <div className="min-w-0 space-y-1.5">
            <label htmlFor="gateway-url" className="text-xs font-semibold flex items-center gap-1">
              <Link2 className="w-3 h-3" /> URL Gateway
            </label>
            <input id="gateway-url" type="text" inputMode="url" autoCapitalize="none" autoCorrect="off"
              spellCheck={false} value={url} disabled={disabled} onChange={event => setUrl(event.target.value)}
              placeholder="ws://alamat-laptop:8082/browser" required
              className="w-full min-w-0 min-h-[44px] px-3 py-2 rounded-lg border border-border bg-background font-mono text-base sm:text-xs" />
          </div>
          <div className="min-w-0 space-y-1.5">
            <label htmlFor="gateway-token" className="text-xs font-semibold flex items-center gap-1">
              <ShieldCheck className="w-3 h-3" /> Kode Pairing
            </label>
            <input id="gateway-token" type="password" autoComplete="off" autoCapitalize="none" autoCorrect="off"
              spellCheck={false} value={token} disabled={disabled} onChange={event => setToken(event.target.value)}
              placeholder="Masukkan kode pairing" required
              className="w-full min-w-0 min-h-[44px] px-3 py-2 rounded-lg border border-border bg-background font-mono text-base sm:text-xs" />
          </div>
        </div>
        {error && <p role="alert" className="flex items-center gap-2 text-xs text-rose-700">
          <AlertCircle className="w-4 h-4 shrink-0" />{error}
        </p>}
        <p className="text-xs text-muted-foreground">
          {connected ? "Perangkat terhubung. Pilih organ, lalu mulai rekaman atau prediksi langsung."
            : "Hubungkan alat untuk mengaktifkan rekaman dan prediksi. Putuskan koneksi browser laptop sebelum memakai HP."}
        </p>
        <div className="flex flex-col sm:flex-row gap-2">
          <button type="submit" disabled={disabled}
            className="min-h-[44px] px-4 py-2.5 rounded-xl bg-emerald-800 text-white text-sm font-semibold">
            {connected ? "Hubungkan ulang" : "Hubungkan ESP32"}
          </button>
          {connected && <button type="button" disabled={disabled} onClick={onDisconnect}
            className="min-h-[44px] px-4 py-2.5 rounded-xl border border-border text-sm font-semibold">
            Putuskan koneksi
          </button>}
        </div>
      </form>
    </section>
  );
}
