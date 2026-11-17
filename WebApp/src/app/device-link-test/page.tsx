"use client";

import { useEffect, useRef, useState } from "react";
import { defaultGatewayUrl } from "@/lib/auriscore/gateway-url";
import { LinkTestConnection, type LinkTestState } from "@/lib/auriscore/link-test";

export default function DeviceLinkTest() {
  const [url, setUrl] = useState("");
  const [token, setToken] = useState("");
  const [state, setState] = useState<LinkTestState>({ paired: false, device: null, gatewayRttMs: null, error: null });
  const link = useRef<LinkTestConnection | null>(null);
  useEffect(() => {
    setUrl(defaultGatewayUrl(window.location));
    const client = new LinkTestConnection(setState); link.current = client;
    return () => { client.close(); link.current = null; };
  }, []);
  return <main className="mx-auto max-w-xl space-y-5 px-5 py-8 text-emerald-950">
    <p className="text-sm font-semibold">AurisCore · uji koneksi perangkat</p>
    <h1 className="text-3xl font-bold">Tes koneksi ESP32</h1>
    <p>ESP32 → Wi-Fi → gateway laptop → browser HP. Halaman ini hanya menguji koneksi.</p>
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm">
      Halaman ini tidak meminta audio. Tidak ada waveform, rekaman, atau prediksi medis pada tes ini.
      Firmware capture dapat membaca I2S pada perangkat, tetapi halaman ini tidak memulai pengiriman audio.
      Keberhasilan tes belum membuktikan kestabilan saat mic dipasang.
    </div>
    <form className="space-y-4 rounded-2xl border bg-white p-5" onSubmit={event => {
      event.preventDefault();
      try {
        if (window.location.protocol === "https:" && !url.trim().startsWith("wss://")) throw Error("Halaman HTTPS memerlukan WSS.");
        link.current?.connect(url.trim(), token.trim());
      } catch (error) { setState(s => ({ ...s, error: error instanceof Error ? error.message : "Koneksi gagal." })); }
    }}>
      <label className="block space-y-2"><span>URL gateway</span>
        <input className="w-full rounded-lg border p-3 text-base" value={url} onChange={e => setUrl(e.target.value)}
          autoCapitalize="none" autoCorrect="off" spellCheck={false} required />
      </label>
      <label className="block space-y-2"><span>Kode pairing</span>
        <input className="w-full rounded-lg border p-3 text-base" type="password" value={token} onChange={e => setToken(e.target.value)}
          autoCapitalize="none" autoCorrect="off" autoComplete="off" required />
      </label>
      <button className="min-h-12 w-full rounded-xl bg-emerald-800 px-4 py-3 font-semibold text-white" type="submit">Hubungkan uji ESP32</button>
      <button className="min-h-12 w-full rounded-xl border px-4 py-3" type="button" onClick={() => link.current?.close()}>Putuskan koneksi</button>
    </form>
    {state.error && <p role="alert" className="rounded-xl bg-rose-50 p-4 text-rose-800">{state.error}</p>}
    <section aria-label="Status uji" aria-live="polite" className="space-y-4 rounded-2xl border bg-white p-5">
      <div><p className="text-sm">Browser ↔ gateway</p><p className="text-xl font-bold">{state.paired ? "Terhubung" : "Belum terhubung"}</p></div>
      <div><p className="text-sm">ESP32 ↔ gateway</p><p className="text-xl font-bold">{state.device ? "ESP32 terhubung · audio tidak diminta" : "Menunggu ESP32"}</p></div>
      <div><p className="text-sm">Respons gateway</p><p className="text-xl font-bold">{state.gatewayRttMs === null ? "—" : `${state.gatewayRttMs.toFixed(1)} ms`}</p>
        <p className="text-sm">Pulang-pergi browser ↔ gateway; bukan latensi mic.</p></div>
      <p className="text-sm">HP dan laptop harus berada pada jaringan yang sama. Satu browser pengendali pada satu waktu; putuskan browser laptop sebelum membuka dari HP.</p>
    </section>
  </main>;
}
