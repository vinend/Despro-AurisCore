import { AnalysisPythonError, getAnalysisWorker } from "./analysis-python.server.ts";
import type { AnalysisMode, OrganAnalysisResult } from "./analysis-result.ts";
import { LIVE_WINDOW_SAMPLES } from "./live-analysis.ts";

type Analyze = (samples: number[], mode: AnalysisMode, signal: AbortSignal) => Promise<OrganAnalysisResult>;
export function createLiveAnalysisHandler(
  analyze: Analyze = (samples, mode, signal) => getAnalysisWorker().analyzeLive(samples, mode, signal),
) {
  return async (request: Request) => {
    const fail = (error: string, status: number) => Response.json({ error }, { status, headers: { "Cache-Control": "no-store" } });
    const mode = new URL(request.url).searchParams.get("mode");
    if (mode !== "heart" && mode !== "lung" && mode !== "abdomen") return fail("Mode analisis tidak valid.", 400);
    if (request.headers.get("content-type") !== "application/octet-stream") return fail("Gunakan PCM16 little-endian.", 415);
    const expected = LIVE_WINDOW_SAMPLES[mode] * 2;
    const start = request.headers.get("x-auriscore-start-sample");
    const startSample = Number(start);
    if (start === null || !/^\d+$/.test(start) || !Number.isSafeInteger(startSample + expected / 2))
      return fail("Indeks sampel tidak valid.", 400);
    const reader = request.body?.getReader();
    if (!reader) return fail("Audio tidak tersedia.", 400);
    const bytes = new Uint8Array(expected);
    let offset = 0;
    try {
      for (;;) {
        const part = await reader.read();
        if (part.done) break;
        if (offset + part.value.length > expected) { await reader.cancel(); return fail("Jendela PCM terlalu panjang.", 413); }
        bytes.set(part.value, offset);
        offset += part.value.length;
      }
    } catch { return fail("Audio tidak dapat dibaca.", 400); }
    if (offset !== expected) return fail("Jendela PCM belum lengkap.", 400);
    const view = new DataView(bytes.buffer);
    const samples = Array.from({ length: expected / 2 }, (_, i) => view.getInt16(i * 2, true));
    try {
      const result = await analyze(samples, mode, request.signal);
      return Response.json({ startSample, endSample: startSample + samples.length, result }, {
        headers: { "Cache-Control": "no-store" },
      });
    } catch (error) {
      return error instanceof AnalysisPythonError ? fail(error.message, error.httpStatus)
        : fail("Analisis langsung belum tersedia.", 502);
    }
  };
}
