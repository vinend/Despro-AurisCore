"use client";

import { useState, type FormEvent } from "react";
import { HeartResultView } from "./heart-result-view";
import { HttpHeartAnalysisService, validateHeartFile } from "@/lib/auriscore/heart-analysis-service";
import { analyzeHeartAudio } from "@/lib/auriscore/heart-audio-source";
import type { HeartAnalysisResult } from "@/lib/auriscore/heart-result";

const heartAnalysisService = new HttpHeartAnalysisService();

/** Independent WAV file simulator; the live mock-device recording remains a demo. */
export function HeartFileDemo() {
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<HeartAnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function analyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fileError = validateHeartFile(file);
    if (fileError) { setError(fileError); setResult(null); return; }
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      setResult(await analyzeHeartAudio({ kind: "file", file: file! }, heartAnalysisService));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Analisis Heart gagal.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="auris-heart-demo" aria-labelledby="heart-file-heading">
      <div className="auris-heart-demo-intro">
        <div><p className="auris-eyebrow">FILE SIMULATOR · HEART</p><h2 id="heart-file-heading">Analisis WAV jantung</h2></div>
        <p>Jalur ini menjalankan DSP Python lokal pada WAV mono. Tidak menggunakan sinyal simulator perangkat atau model Murmur yang sedang dilatih.</p>
      </div>
      <form className="auris-heart-file-form" onSubmit={analyze}>
        <label htmlFor="heart-wav">Pilih WAV mono</label>
        <input id="heart-wav" type="file" accept=".wav,audio/wav,audio/x-wav" disabled={loading}
          onChange={(event) => {
            setFile(event.currentTarget.files?.[0] ?? null);
            setError(null);
            setResult(null);
          }} />
        <button type="submit" disabled={loading}>{loading ? "Menganalisis…" : "Analisis WAV"}</button>
      </form>
      <div aria-live="polite">
        {loading && <p className="auris-heart-progress" role="status">DSP sedang memproses WAV…</p>}
        {error && <p className="auris-heart-warning" role="alert">{error}</p>}
        {result && <HeartResultView result={result} />}
      </div>
      <p className="auris-heart-disclaimer">Keluaran skrining prototipe — bukan diagnosis. File tidak disimpan sebagai sesi.</p>
    </section>
  );
}
