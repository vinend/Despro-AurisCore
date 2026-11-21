import { parseOrganAnalysisResult, type AnalysisMode } from "./analysis-result.ts";
import { AnalysisPythonError } from "./analysis-python.server.ts";
import { matchesToken } from "./cloud-auth.server.ts";
import { deviceAccountAuthorized } from "./device-account.server.ts";

export const CLOUD_WAV_BYTES = 4 * 1024 * 1024;
export const cloudAnalysisEnabled = () => process.env.VERCEL === "1" || process.env.AURISCORE_CLOUD_ANALYSIS === "1";
export const cloudOperatorAuthorized = async (request: Request) => process.env.VERCEL === "1" || process.env.AURISCORE_DEVICE_ACCOUNT_EMAILS
  ? deviceAccountAuthorized(request.headers.get("x-auriscore-operator-token"))
  : matchesToken(request.headers.get("x-auriscore-operator-token"), process.env.AURISCORE_OPERATOR_TOKEN);

export async function analyzeInCloud(bytes: Uint8Array, format: "pcm" | "wav", mode: AnalysisMode, signal: AbortSignal) {
  const base = process.env.AURISCORE_INFERENCE_URL;
  const token = process.env.AURISCORE_INFERENCE_TOKEN;
  if (!base?.startsWith("https://") || !token || token.length < 16)
    throw new AnalysisPythonError("Layanan cloud belum dikonfigurasi.", 503);
  const response = await fetch(new URL(`/v1/analysis/${mode}/${format}`, base), {
    method: "POST", body: new Uint8Array(bytes),
    headers: { "Content-Type": format === "wav" ? "audio/wav" : "application/octet-stream", Authorization: `Bearer ${token}` },
    signal: AbortSignal.any([signal, AbortSignal.timeout(55_000)]), redirect: "error", cache: "no-store",
  });
  if (response.status === 429) throw new AnalysisPythonError("Analisis sedang sibuk.", 429);
  if (!response.ok) throw new AnalysisPythonError("Layanan cloud tidak dapat memproses audio.", 502);
  return parseOrganAnalysisResult(await response.json(), mode);
}
