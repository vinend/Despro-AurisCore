"use client";
import { useEffect, useRef, useState } from "react";
import { accountClient } from "@/lib/auriscore/account-client";
import { heartReference } from "@/lib/auriscore/heart-reference";
import { HttpOrganAnalysisService } from "@/lib/auriscore/organ-analysis-service";
import type { SavedSession } from "@/lib/auriscore/session-repository";
import type { SessionToSave } from "@/hooks/use-session-history";
import { OrganResultView } from "./organ-result-view";
import { useAccount } from "./account-panel";
import { RecordingPlayback } from "./recording-playback";

function ReferenceCitation() {
  return <p className="text-xs text-muted-foreground">
    Sumber: <a href={heartReference.citationUrl} className="underline underline-offset-2">CirCor DigiScope 1.0.3</a>
    {" · Oliveira dkk., PhysioNet · ODC Attribution 1.0"}
  </p>;
}

function AddHeartReference({ save, disabled, saved }: {
  save: (file: File, entry: SessionToSave, userId: string) => Promise<boolean>;
  disabled: boolean;
  saved: boolean;
}) {
  const { user } = useAccount();
  const [state, setState] = useState<"idle" | "adding" | "queued">("idle");
  const [error, setError] = useState<string | null>(null);
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);

  async function add() {
    if (!user || active.current || disabled || saved || state === "queued") return;
    const controller = new AbortController();
    active.current = controller;
    setError(null);
    setState("adding");
    try {
      const response = await fetch("/api/reference/heart", { signal: controller.signal });
      if (!response.ok) throw new Error("Rekaman referensi belum dapat dimuat.");
      const file = new File([await response.blob()], heartReference.filename, { type: "audio/wav" });
      const result = await new HttpOrganAnalysisService().analyze(file, "heart", controller.signal);
      if (result.mode !== "heart" || result.analysis?.murmur?.status !== "available")
        throw new Error("Analisis Murmur belum tersedia. Coba lagi saat layanan siap.");
      if (controller.signal.aborted) return;
      const queued = await save(file, { ts: Date.now(), mode: "heart", source: heartReference.source,
        durationMs: heartReference.durationMs, result }, user.id);
      if (!queued) throw new Error("Rekaman referensi belum dapat disimpan. Coba lagi.");
      if (!controller.signal.aborted) setState("queued");
    } catch (error) {
      if (!controller.signal.aborted) {
        setState("idle");
        setError(error instanceof Error ? error.message : "Penambahan rekaman referensi gagal.");
      }
    } finally {
      if (active.current === controller) active.current = null;
    }
  }

  return <div className="rounded-xl border p-3 space-y-2">
    <button type="button" className="rounded-lg border px-3 py-2 text-sm font-medium disabled:opacity-60"
      disabled={disabled || saved || state !== "idle"} onClick={() => { void add(); }}>
      {saved ? "Referensi Heart sudah tersimpan" : state === "adding" ? "Menganalisis rekaman…"
        : state === "queued" ? "Referensi dalam antrean sinkronisasi" : "Tambahkan rekaman referensi Heart"}
    </button>
    <ReferenceCitation />
    {error && <p role="alert" className="text-sm">{error}</p>}
  </div>;
}

function SavedSessionDetails({ entry }: { entry: SavedSession }) {
  const { user } = useAccount();
  const [file, setFile] = useState<Blob | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let current = true;
    void (async () => {
      try {
        if (user?.id !== entry.user_id) throw new Error();
        const { data, error: failure } = await accountClient().storage.from("auriscore-recordings").download(entry.audio_path);
        if (failure || !data) throw new Error();
        if (current) setFile(data);
      } catch { if (current) setError("Rekaman belum dapat diputar. Coba buka sesi ini lagi."); }
    })();
    return () => { current = false; };
  }, [entry.audio_path, entry.user_id, user?.id]);
  return <div className="space-y-3">
    {entry.source === heartReference.source && <ReferenceCitation />}
    {error && <p role="alert">{error}</p>}
    {file ? <RecordingPlayback file={file} result={entry.result} />
      : !error && <p role="status">Memuat rekaman privat…</p>}
    <OrganResultView result={entry.result} showTimeline={!file} />
  </div>;
}

export function SavedSessionHistory({ entries, message, saving, more, save, busy, onRetry, onMore }: {
  entries: SavedSession[]; message: string | null; saving: boolean; more: boolean;
  save: (file: File, entry: SessionToSave, userId: string) => Promise<boolean>;
  busy: boolean;
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
    <AddHeartReference save={save} disabled={busy || saving}
      saved={entries.some(entry => entry.source === heartReference.source)} />
    {message && <p role="status" className="text-sm">{message}</p>}
    {!entries.length && <p>Belum ada sesi tersimpan di akun ini.</p>}
    {entries.map(entry => <article key={entry.id} className="rounded-xl border p-3 space-y-3">
      <button className="w-full text-left flex flex-wrap justify-between gap-2" aria-expanded={selected === entry.id}
        onClick={() => setSelected(selected === entry.id ? null : entry.id)}>
        <span>{entry.source === heartReference.source ? "Heart · Referensi CirCor" : entry.mode.toUpperCase()}
          {" · "}{new Date(entry.recorded_at).toLocaleString("id-ID")}</span>
        <span>{(entry.duration_ms / 1000).toFixed(1)} detik · Lihat hasil dan putar</span>
      </button>
      {selected === entry.id && <SavedSessionDetails entry={entry} />}
    </article>)}
    {more && <button className="border rounded-lg px-3 py-2" onClick={onMore}>Muat sesi sebelumnya</button>}
  </section>;
}
