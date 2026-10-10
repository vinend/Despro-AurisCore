import { parseOrganAnalysisResult, type AnalysisMode, type OrganAnalysisResult } from "./analysis-result.ts";
import { validateHeartFile } from "./heart-analysis-service.ts";
import { pcmToWavFile, type AnalysisReadyAudio } from "./heart-audio-source.ts";

export interface OrganAnalysisService {
  analyze(file: File, mode: AnalysisMode, signal?: AbortSignal): Promise<OrganAnalysisResult>;
}
export class HttpOrganAnalysisService implements OrganAnalysisService {
  constructor(private readonly request: typeof fetch = fetch) {}
  async analyze(file: File, mode: AnalysisMode, signal?: AbortSignal): Promise<OrganAnalysisResult> {
    const error = validateHeartFile(file);
    if (error) throw new Error(error);
    const form = new FormData();
    form.set("audio", file);
    form.set("mode", mode);
    const response = await this.request.call(globalThis, "/api/analysis", { method: "POST", body: form, signal });
    const body: unknown = await response.json();
    if (typeof body === "object" && body !== null && "schema_version" in body)
      return parseOrganAnalysisResult(body, mode);
    const message = typeof body === "object" && body !== null && "error" in body && typeof body.error === "string"
      ? body.error : "Layanan analisis tidak dapat memproses rekaman.";
    throw new Error(message);
  }
}
export function analyzeOrganAudio(input: { kind: "file"; file: File } | { kind: "pcm"; audio: AnalysisReadyAudio },
  mode: AnalysisMode, service: OrganAnalysisService, signal?: AbortSignal) {
  return service.analyze(input.kind === "file" ? input.file : pcmToWavFile(input.audio), mode, signal);
}
