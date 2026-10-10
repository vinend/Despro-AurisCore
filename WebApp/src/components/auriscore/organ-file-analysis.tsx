"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { HttpOrganAnalysisService } from "@/lib/auriscore/organ-analysis-service";
import { validateHeartFile } from "@/lib/auriscore/heart-analysis-service";
import type { AnalysisMode, OrganAnalysisResult } from "@/lib/auriscore/analysis-result";
import { OrganResultView } from "./organ-result-view";
import { RecordingPlayback } from "./recording-playback";
const service = new HttpOrganAnalysisService();

export function OrganFileAnalysis({ mode, onBusy, disabled = false }: { mode: AnalysisMode; onBusy: (busy: boolean) => void; disabled?: boolean }) {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<OrganAnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const abort = useRef<AbortController | null>(null);
  useEffect(() => () => { abort.current?.abort(); }, []);
  async function analyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loading || disabled) return;
    const problem = validateHeartFile(file);
    if (problem) { setError(problem); setResult(null); return; }
    const controller = new AbortController(); abort.current = controller;
    setError(null); setResult(null); setLoading(true); onBusy(true);
    try { const output = await service.analyze(file!, mode, controller.signal); if (!controller.signal.aborted) setResult(output); }
    catch (cause) { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Analisis WAV gagal."); }
    finally { if (!controller.signal.aborted) { setLoading(false); onBusy(false); } }
  }
  return <section className="auris-heart-demo" aria-labelledby="organ-file-heading">
    <div className="auris-heart-demo-intro"><div><p className="auris-eyebrow">REKAMAN WAV · {mode.toUpperCase()}</p>
      <h2 id="organ-file-heading">Analisis WAV {mode === "heart" ? "jantung" : "abdomen"}</h2></div>
      <p>Unggah rekaman mono untuk analisis audio. Hasil hanya ditampilkan bila analisis tersedia.</p></div>
    <form className="auris-heart-file-form" onSubmit={analyze}>
      <label htmlFor="organ-wav">Pilih WAV mono</label>
      <input id="organ-wav" type="file" accept=".wav,audio/wav,audio/x-wav" disabled={loading || disabled}
        onChange={event => { setFile(event.currentTarget.files?.[0] ?? null); setResult(null); setError(null); }} />
      <button type="submit" disabled={loading || disabled}>{loading ? "Menganalisis…" : "Analisis WAV"}</button>
    </form>
    {file && <RecordingPlayback file={file} />}
    <div aria-live="polite">{loading && <p role="status">Rekaman sedang dianalisis…</p>}
      {error && <p className="auris-heart-warning" role="alert">{error}</p>}
      {result && <OrganResultView result={result} />}</div>
    <p className="auris-heart-disclaimer">Keluaran skrining prototipe — bukan diagnosis. File tidak disimpan sebagai sesi.</p>
  </section>;
}
