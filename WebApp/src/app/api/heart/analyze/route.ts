import { parseHeartAnalysisResult } from "@/lib/auriscore/heart-result";
import { MAX_HEART_WAV_BYTES } from "@/lib/auriscore/heart-analysis-service";
import { analyzeWavWithPython, HeartPythonError } from "@/lib/auriscore/heart-python.server";

export const runtime = "nodejs";

function failure(error: string, status: number): Response {
  return Response.json({ error }, { status });
}

export async function POST(request: Request): Promise<Response> {
  const declaredLength = Number(request.headers.get("content-length"));
  if (Number.isFinite(declaredLength) && declaredLength > MAX_HEART_WAV_BYTES + 64 * 1024) {
    return failure("Berkas WAV terlalu besar (maksimum 16 MB).", 413);
  }
  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return failure("Unggahan WAV tidak dapat dibaca.", 400);
  }
  const file = form.get("audio");
  if (!(file instanceof File)) return failure("Pilih berkas WAV terlebih dahulu.", 400);
  if (!file.name.toLowerCase().endsWith(".wav")) return failure("Pilih berkas .wav.", 415);
  if (file.size === 0) return failure("Berkas WAV kosong.", 400);
  if (file.size > MAX_HEART_WAV_BYTES) return failure("Berkas WAV terlalu besar (maksimum 16 MB).", 413);
  const wav = Buffer.from(await file.arrayBuffer());
  if (wav.length < 12 || wav.toString("ascii", 0, 4) !== "RIFF"
      || wav.toString("ascii", 8, 12) !== "WAVE") {
    return failure("Format WAV RIFF tidak didukung atau berkas rusak.", 415);
  }

  try {
    const raw = await analyzeWavWithPython(wav);
    return Response.json(parseHeartAnalysisResult(raw));
  } catch (error) {
    if (error instanceof HeartPythonError) return failure(error.message, error.httpStatus);
    return failure("Layanan DSP mengembalikan hasil yang tidak valid.", 502);
  }
}
