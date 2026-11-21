"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Wifi } from "lucide-react";
import { useAccount } from "./account-panel";
import type { StreamSettings } from "./device-connect";
import { currentDeviceAccountToken } from "@/lib/auriscore/device-account";

export function AccountDeviceConnect({ disabled, connected, onConnect, onDisconnect }: {
  disabled: boolean; connected: boolean;
  onConnect: (settings: StreamSettings) => void; onDisconnect: () => void;
}) {
  const { user } = useAccount();
  const userId = user?.id;
  const [message, setMessage] = useState("");
  const [checking, setChecking] = useState(false);
  const callbacks = useRef({ onConnect, onDisconnect });
  const attempt = useRef<AbortController | null>(null);
  useEffect(() => { callbacks.current = { onConnect, onDisconnect }; }, [onConnect, onDisconnect]);
  const connect = useCallback(async () => {
    if (!userId) return;
    attempt.current?.abort();
    const controller = new AbortController(); attempt.current = controller;
    setChecking(true); setMessage("");
    try {
      const token = await currentDeviceAccountToken();
      if (controller.signal.aborted) return;
      const response = await fetch("/api/device-access", {
        headers: { Authorization: `Bearer ${token}` }, cache: "no-store", signal: controller.signal,
      });
      if (!response.ok) throw new Error(response.status === 403
        ? "Akun ini belum diberi akses ke alat, email belum dikonfirmasi, atau sesi perlu diperbarui. Hubungi pengelola."
        : "Layanan alat belum dapat dijangkau. Coba kembali.");
      if (controller.signal.aborted) return;
      callbacks.current.onConnect({ source: "hardware", token: "", ownerId: userId,
        url: `wss://${window.location.host}/api/gateway/browser`, getToken: currentDeviceAccountToken });
      setMessage("Menunggu alat online. Nyalakan alat dan pastikan Wi-Fi memiliki internet.");
    } catch (error) {
      if (!controller.signal.aborted) setMessage(error instanceof Error ? error.message : "Koneksi alat belum tersedia.");
    } finally { if (!controller.signal.aborted) setChecking(false); }
  }, [userId]);
  useEffect(() => {
    const timer = setTimeout(() => { void connect(); }, 0);
    return () => { clearTimeout(timer); attempt.current?.abort(); };
  }, [connect]);
  return <section aria-label="Koneksi alat" className="rounded-2xl border border-border/80 bg-white p-4 shadow-xs space-y-3">
    <div className="flex gap-3 items-center"><Wifi className="h-5 w-5 text-emerald-700" />
      <div><h2 className="font-semibold">Stetoskop Anda</h2>
        <p className="text-sm text-muted-foreground">Alat terhubung melalui akun Anda. Tidak perlu memasukkan kode pairing.</p></div></div>
    {!user ? <p>Masuk dengan akun AurisCore yang memiliki akses alat. <a className="underline" href="/">Buka halaman masuk</a>.</p>
      : <><p role="status" className="text-sm">{connected ? "Alat terhubung. Pilih organ dan mulai pemeriksaan." : checking ? "Memeriksa akses alat…" : message}</p>
        <div className="flex gap-2 flex-wrap">
          <button type="button" disabled={disabled || checking} onClick={() => { void connect(); }}
            className="min-h-11 rounded-xl bg-emerald-900 text-white px-4 py-2 font-medium disabled:opacity-50">{connected ? "Hubungkan ulang" : "Hubungkan alat"}</button>
          {connected && <button type="button" disabled={disabled} onClick={() => {
            attempt.current?.abort(); callbacks.current.onDisconnect(); setMessage("Koneksi dihentikan. Tekan Hubungkan alat untuk menyambung kembali.");
          }} className="min-h-11 rounded-xl border px-4 py-2">Putuskan koneksi</button>}
        </div></>}
    <details className="border-t pt-3 text-sm"><summary className="cursor-pointer font-medium">Mengatur Wi-Fi baru</summary>
      <ol className="list-decimal pl-5 mt-2 space-y-2">
        <li>Nyalakan alat. Jaringan 2,4 GHz yang sudah disimpan akan dihubungkan otomatis.</li>
        <li>Jika jaringan tersimpan tidak ditemukan, tunggu Wi-Fi AurisCore-Setup muncul. Sambungkan HP ke sana menggunakan kunci setup alat.</li>
        <li>Buka <a href="http://192.168.4.1/setup" target="_blank" rel="noreferrer" className="underline">pengaturan Wi-Fi alat</a>, lalu simpan nama dan password jaringan sekali.</li>
        <li>Kembalikan HP ke internet. Buka AurisCore dan login. Alat tetap memerlukan daya dan internet.</li>
      </ol><p className="mt-2 text-muted-foreground">Tidak memerlukan tombol Wi-Fi pada sasis. Kunci setup hanya untuk pengaturan jaringan pertama/baru.</p>
    </details>
  </section>;
}
