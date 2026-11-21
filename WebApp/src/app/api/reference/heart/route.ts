import { createHash } from "node:crypto";
import { heartReference } from "@/lib/auriscore/heart-reference";

export async function GET() {
  try {
    const source = await fetch(heartReference.recordingUrl, {
      redirect: "error",
      signal: AbortSignal.timeout(10_000),
      next: { revalidate: 86_400 },
    });
    if (!source.ok || Number(source.headers.get("content-length")) !== heartReference.bytes)
      throw new Error("Unexpected reference size");
    const wav = await source.arrayBuffer();
    if (wav.byteLength !== heartReference.bytes
        || createHash("sha256").update(new Uint8Array(wav)).digest("hex") !== heartReference.sha256)
      throw new Error("Reference integrity check failed");
    return new Response(wav, { headers: { "Content-Type": "audio/wav",
      "Cache-Control": "public, max-age=3600, s-maxage=86400" } });
  } catch {
    return Response.json({ error: "Rekaman referensi belum dapat dimuat." }, { status: 502 });
  }
}
