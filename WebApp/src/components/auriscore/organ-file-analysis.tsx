"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { UploadCloud, FileAudio, Check, AlertCircle, Loader2 } from "lucide-react";
import { HttpOrganAnalysisService } from "@/lib/auriscore/organ-analysis-service";
import { validateHeartFile } from "@/lib/auriscore/heart-analysis-service";
import type { AnalysisMode, OrganAnalysisResult } from "@/lib/auriscore/analysis-result";
import { OrganResultView } from "./organ-result-view";
import { RecordingPlayback } from "./recording-playback";

const service = new HttpOrganAnalysisService();

export function OrganFileAnalysis({
  mode,
  onBusy,
  disabled = false,
}: {
  mode: AnalysisMode;
  onBusy: (busy: boolean) => void;
  disabled?: boolean;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<OrganAnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => () => {
    abort.current?.abort();
  }, []);

  async function analyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loading || disabled) return;
    const problem = validateHeartFile(file);
    if (problem) {
      setError(problem);
      setResult(null);
      return;
    }
    const controller = new AbortController();
    abort.current = controller;
    setError(null);
    setResult(null);
    setLoading(true);
    onBusy(true);
    try {
      const output = await service.analyze(file!, mode, controller.signal);
      if (!controller.signal.aborted) setResult(output);
    } catch (cause) {
      if (!controller.signal.aborted)
        setError(cause instanceof Error ? cause.message : "Analisis WAV gagal.");
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
        onBusy(false);
      }
    }
  }

  const modeName = mode === "heart" ? "jantung" : mode === "lung" ? "paru" : "abdomen";

  return (
    <section className="auris-heart-demo" aria-labelledby="organ-file-heading">
      <div className="auris-heart-demo-intro">
        <div>
          <p className="auris-eyebrow">REKAMAN WAV · {mode.toUpperCase()}</p>
          <h2 id="organ-file-heading">Analisis WAV {modeName}</h2>
        </div>
        <p>Unggah rekaman mono untuk analisis audio. Hasil hanya ditampilkan bila analisis tersedia.</p>
      </div>

      <form className="auris-heart-file-form mt-4 space-y-3" onSubmit={analyze}>
        <div
          onClick={() => !loading && !disabled && fileInputRef.current?.click()}
          className={`flex flex-col items-center justify-center p-5 rounded-2xl border-2 border-dashed transition-all cursor-pointer ${
            file
              ? "border-emerald-300 bg-emerald-50/40"
              : "border-border hover:border-emerald-500/50 bg-muted/20 hover:bg-muted/40"
          } ${loading || disabled ? "opacity-50 cursor-not-allowed" : ""}`}
        >
          <input
            ref={fileInputRef}
            id="organ-wav"
            type="file"
            accept=".wav,audio/wav,audio/x-wav"
            disabled={loading || disabled}
            className="sr-only"
            onChange={(event) => {
              setFile(event.currentTarget.files?.[0] ?? null);
              setResult(null);
              setError(null);
            }}
          />

          <div className="w-10 h-10 rounded-full bg-emerald-100/70 text-emerald-800 flex items-center justify-center mb-2">
            {file ? <Check className="w-5 h-5 text-emerald-700" /> : <UploadCloud className="w-5 h-5" />}
          </div>

          <label
            htmlFor="organ-wav"
            className="text-xs sm:text-sm font-semibold text-emerald-950 cursor-pointer pointer-events-none"
          >
            {file ? file.name : "Pilih WAV mono"}
          </label>

          <p className="text-[11px] text-muted-foreground mt-1 pointer-events-none text-center">
            {file
              ? `${Math.round(file.size / 1024)} KB · Ketuk untuk mengganti berkas`
              : "Ketuk untuk memilih dari perangkat (format audio .wav)"}
          </p>
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={loading || disabled || !file}
            className="w-full sm:w-auto min-h-[44px] px-6 py-2.5 rounded-xl bg-emerald-800 hover:bg-emerald-900 active:scale-[0.98] text-white text-xs sm:text-sm font-semibold shadow-xs disabled:opacity-50 transition-all flex items-center justify-center gap-2"
          >
            {loading && <Loader2 className="w-4 h-4 animate-spin text-white" />}
            <span>{loading ? "Menganalisis…" : "Analisis WAV"}</span>
          </button>
        </div>
      </form>

      {file && <RecordingPlayback file={file} />}

      <div aria-live="polite" className="mt-3">
        {loading && (
          <div className="flex items-center gap-2 p-3 text-xs text-emerald-700 font-medium bg-emerald-50 rounded-xl border border-emerald-200">
            <Loader2 className="w-4 h-4 animate-spin text-emerald-600" />
            <p role="status">Rekaman sedang dianalisis…</p>
          </div>
        )}
        {error && (
          <div className="auris-heart-warning flex items-start gap-2" role="alert">
            <AlertCircle className="w-4 h-4 text-orange-600 flex-shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}
        {result && <OrganResultView result={result} />}
      </div>

      <p className="auris-heart-disclaimer">
        Keluaran skrining prototipe — bukan diagnosis. File tidak disimpan sebagai sesi.
      </p>
    </section>
  );
}
