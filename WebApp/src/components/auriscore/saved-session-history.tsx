"use client";
import { useEffect, useState } from "react";
import { accountClient } from "@/lib/auriscore/account-client";
import type { SavedSession } from "@/lib/auriscore/session-repository";
import { OrganResultView } from "./organ-result-view";
import { useAccount } from "./account-panel";

function SavedSessionDetails({ entry }: { entry: SavedSession }) {
  const { user } = useAccount();
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let current = true;
    let objectUrl: string | null = null;
    void (async () => {
      try {
        if (user?.id !== entry.user_id) throw new Error();
        const { data, error: failure } = await accountClient().storage.from("auriscore-recordings").download(entry.audio_path);
        if (failure || !data) throw new Error();
        if (current) { objectUrl = URL.createObjectURL(data); setUrl(objectUrl); }
      } catch { if (current) setError("Rekaman belum dapat diputar. Coba buka sesi ini lagi."); }
    })();
    return () => { current = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [entry.audio_path, entry.user_id, user?.id]);
  return <div className="space-y-3">
    {error && <p role="alert">{error}</p>}
    {url ? <audio className="w-full" controls preload="metadata" src={url} aria-label="Putar rekaman tersimpan" />
      : !error && <p role="status">Memuat rekaman privat…</p>}
    <OrganResultView result={entry.result} />
  </div>;
}

export function SavedSessionHistory({ entries, message, saving, more, onRetry, onMore }: {
  entries: SavedSession[]; message: string | null; saving: boolean; more: boolean;
  onRetry: () => void; onMore: () => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  return <section className="auris-history space-y-3" aria-label="Riwayat akun">
    <div className="flex flex-wrap justify-between items-center gap-2">
      <h2 className="font-semibold">Riwayat akun</h2>
      <button disabled={saving} className="rounded-lg border px-3 py-2" onClick={onRetry}>
        {saving ? "Menyinkronkan…" : "Muat ulang / coba sinkronisasi"}
      </button>
    </div>
    {message && <p role="status" className="text-sm">{message}</p>}
    {!entries.length && <p>Belum ada sesi tersimpan di akun ini.</p>}
    {entries.map(entry => <article key={entry.id} className="rounded-xl border p-3 space-y-3">
      <button className="w-full text-left flex flex-wrap justify-between gap-2" aria-expanded={selected === entry.id}
        onClick={() => setSelected(selected === entry.id ? null : entry.id)}>
        <span>{entry.mode.toUpperCase()} · {new Date(entry.recorded_at).toLocaleString("id-ID")}</span>
        <span>{(entry.duration_ms / 1000).toFixed(1)} detik · Lihat hasil dan putar</span>
      </button>
      {selected === entry.id && <SavedSessionDetails entry={entry} />}
    </article>)}
    {more && <button className="border rounded-lg px-3 py-2" onClick={onMore}>Muat sesi sebelumnya</button>}
  </section>;
}
