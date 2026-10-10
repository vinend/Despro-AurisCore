"use client";
import { useState } from "react";
export interface StreamSettings { source: "mock" | "hardware"; url: string; token: string }
export function DeviceConnect({ disabled, onConnect }: { disabled: boolean; onConnect: (settings: StreamSettings) => void }) {
  const [source, setSource] = useState<"mock" | "hardware">("mock");
  const [url, setUrl] = useState("ws://localhost:8082/browser"), [token, setToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  return <form onSubmit={event => {
    event.preventDefault(); setError(null);
    if (source === "hardware") {
      try { const parsed = new URL(url); if (!["ws:", "wss:"].includes(parsed.protocol) || parsed.pathname !== "/browser" || parsed.username || parsed.password || parsed.search) throw Error();
        if (window.location.protocol === "https:" && parsed.protocol !== "wss:") throw Error();
      } catch { setError("Gunakan URL gateway /browser dengan ws:// atau wss:// yang sesuai halaman."); return; }
      if (token.length < 16) { setError("Kode pairing minimal 16 karakter."); return; }
    }
    onConnect({ source, url, token });
  }}>
    <label>Sumber audio <select value={source} disabled={disabled} onChange={event => setSource(event.target.value as "mock" | "hardware")}>
      <option value="mock">Simulator (audio sintetis)</option><option value="hardware">ESP32 melalui Wi-Fi</option></select></label>
    {source === "hardware" && <><label> URL gateway <input value={url} disabled={disabled} onChange={event => setUrl(event.target.value)} /></label>
      <label> Kode pairing <input type="password" autoComplete="off" value={token} disabled={disabled} onChange={event => setToken(event.target.value)} /></label></>}
    <button type="submit" disabled={disabled}>Hubungkan sumber</button>
    {error && <p role="alert">{error}</p>}
  </form>;
}
