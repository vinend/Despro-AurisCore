import { MAX_HEART_WAV_BYTES } from "./heart-analysis-service.ts";
import { AnalysisPythonError, getAnalysisWorker } from "./analysis-python.server.ts";
import type { AnalysisMode, OrganAnalysisResult } from "./analysis-result.ts";

type Analyzer = (wav: Buffer, mode: AnalysisMode, signal?: AbortSignal) => Promise<OrganAnalysisResult>;
export function createAnalysisHandler(fixedMode?: AnalysisMode, legacyHeart = false,
  analyze: Analyzer = (wav, mode, signal) => getAnalysisWorker().analyze(wav, mode, signal)) {
  return async (request: Request): Promise<Response> => {
    const failure = (error: string, status: number) => Response.json({ error }, { status });
    const maxBody = MAX_HEART_WAV_BYTES + 64 * 1024;
    const size = Number(request.headers.get("content-length"));
    if (size > maxBody) return failure("Berkas WAV terlalu besar (maksimum 16 MB).", 413);
    let form: FormData;
    try {
      const reader = request.body?.getReader();
      if (!reader) return failure("Unggahan WAV tidak dapat dibaca.", 400);
      const parts: Uint8Array<ArrayBuffer>[] = [];
      let bytes = 0;
      for (;;) {
        const part = await reader.read();
        if (part.done) break;
        bytes += part.value.byteLength;
        if (bytes > maxBody) { await reader.cancel(); return failure("Berkas WAV terlalu besar (maksimum 16 MB).", 413); }
        parts.push(new Uint8Array(part.value));
      }
      form = await new Response(new Blob(parts), { headers: { "Content-Type": request.headers.get("content-type") ?? "" } }).formData();
    } catch { return failure("Unggahan WAV tidak dapat dibaca.", 400); }
    const requested = form.get("mode");
    const mode = fixedMode ?? requested;
    if ((mode !== "heart" && mode !== "abdomen") || (fixedMode && requested !== null && requested !== fixedMode))
      return failure("Pilih mode Heart atau Abdomen yang sesuai.", 400);
    const file = form.get("audio");
    if (!(file instanceof File)) return failure("Pilih berkas WAV terlebih dahulu.", 400);
    if (!file.name.toLowerCase().endsWith(".wav")) return failure("Pilih berkas .wav.", 415);
    if (!file.size) return failure("Berkas WAV kosong.", 400);
    if (file.size > MAX_HEART_WAV_BYTES) return failure("Berkas WAV terlalu besar (maksimum 16 MB).", 413);
    const wav = Buffer.from(await file.arrayBuffer());
    if (wav.length < 12 || wav.toString("ascii", 0, 4) !== "RIFF" || wav.toString("ascii", 8, 12) !== "WAVE")
      return failure("Format WAV RIFF tidak didukung atau berkas rusak.", 415);
    try {
      const result = await analyze(wav, mode, request.signal);
      if (legacyHeart) {
        if (result.mode !== "heart") return failure("Respons mode analisis tidak sesuai.", 502);
        if (result.analysis) return Response.json(result.analysis);
        if (!result.quality.valid) return Response.json({ schema_version: "heart-analysis-v1", mode: "heart",
          quality: { ...result.quality, score: null }, rhythm: null, cardiac_events: null, murmur: null,
          visualization: { waveform_available: false, spectrogram_available: false, event_annotations_available: false } });
        return failure("Layanan analisis Heart belum tersedia.", 503);
      }
      const status = result.status === "unavailable" ? 503 : result.status === "error" ? 422 : 200;
      return Response.json(result, { status, headers: { "Cache-Control": "no-store" } });
    } catch (error) {
      if (error instanceof AnalysisPythonError) return failure(error.message, error.httpStatus);
      return failure("Layanan analisis mengembalikan hasil yang tidak valid.", 502);
    }
  };
}
