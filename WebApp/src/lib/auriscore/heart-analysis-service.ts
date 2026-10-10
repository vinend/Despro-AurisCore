/** File-simulator transport. The UI receives only the versioned Heart result. */
import { parseHeartAnalysisResult, type HeartAnalysisResult } from "./heart-result.ts";

export const MAX_HEART_WAV_BYTES = 16 * 1024 * 1024;

export interface HeartAnalysisService {
  analyze(file: File): Promise<HeartAnalysisResult>;
}

export function validateHeartFile(file: File | null): string | null {
  if (!file) return "Pilih berkas WAV terlebih dahulu.";
  if (!file.name.toLowerCase().endsWith(".wav")) return "Pilih berkas .wav.";
  if (file.size === 0) return "Berkas WAV kosong.";
  if (file.size > MAX_HEART_WAV_BYTES) return "Berkas WAV terlalu besar (maksimum 16 MB).";
  return null;
}

export class HttpHeartAnalysisService implements HeartAnalysisService {
  private readonly request: typeof fetch;

  constructor(request: typeof fetch = fetch) {
    this.request = request;
  }

  async analyze(file: File): Promise<HeartAnalysisResult> {
    const error = validateHeartFile(file);
    if (error) throw new Error(error);
    const form = new FormData();
    form.set("audio", file);
    let response: Response;
    try {
      response = await this.request.call(globalThis, "/api/heart/analyze", { method: "POST", body: form });
    } catch {
      throw new Error("Layanan Heart analysis tidak dapat dihubungi.");
    }
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw new Error("Respons layanan Heart analysis tidak dapat dibaca.");
    }
    if (!response.ok) {
      const message = typeof body === "object" && body !== null && "error" in body
        && typeof body.error === "string" ? body.error : "Analisis Heart gagal.";
      throw new Error(message);
    }
    return parseHeartAnalysisResult(body);
  }
}
