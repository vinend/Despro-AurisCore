/** Existing WAV bridge: Heart DSP plus an explicitly configured final Murmur model. */
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

export class HeartPythonError extends Error {
  constructor(message: string, readonly httpStatus: number) {
    super(message);
  }
}

export async function analyzeWavWithPython(wav: Buffer): Promise<unknown> {
  const pipeline = process.env.AURISCORE_PIPELINE_DIR
    ? path.resolve(process.env.AURISCORE_PIPELINE_DIR)
    : path.resolve(process.cwd(), "..", "AI-Pipeline");
  const script = path.join(pipeline, "scripts", "analyze_heart_wav.py");
  const python = process.env.AURISCORE_PYTHON
    ? path.resolve(process.env.AURISCORE_PYTHON)
    : path.join(pipeline, ".runtime", "python", "python.exe");
  if (!existsSync(script) || !existsSync(python)) {
    throw new HeartPythonError("Layanan DSP lokal belum dikonfigurasi.", 503);
  }

  const output = await new Promise<string>((resolve, reject) => {
    const child = spawn(python, [script, "--stdin"], {
      cwd: pipeline,
      windowsHide: true,
      stdio: ["pipe", "pipe", "pipe"],
      env: { ...process.env, CUDA_VISIBLE_DEVICES: "-1" },
    });
    const stdout: Buffer[] = [];
    let outputBytes = 0;
    let tooLarge = false;
    child.stdout.on("data", (part: Buffer) => {
      outputBytes += part.length;
      if (outputBytes > 4 * 1024 * 1024) tooLarge = true;
      else stdout.push(part);
    });
    // Do not forward Python tracebacks or local paths to the browser.
    child.stderr.resume();
    child.stdin.on("error", () => { /* The close event reports a failed child. */ });
    child.on("error", () => reject(new HeartPythonError("Layanan DSP tidak dapat dimulai.", 503)));
    child.on("close", (code) => {
      if (tooLarge) reject(new HeartPythonError("Hasil DSP melebihi batas ukuran.", 502));
      else if (code === 3) reject(new HeartPythonError("Paket model Heart belum tersedia atau tidak valid.", 503));
      else if (code !== 0) reject(new HeartPythonError("WAV tidak dapat diproses oleh DSP.", 422));
      else resolve(Buffer.concat(stdout).toString("utf8"));
    });
    child.stdin.end(wav);
  });
  try {
    return JSON.parse(output) as unknown;
  } catch {
    throw new HeartPythonError("Hasil DSP tidak dapat dibaca.", 502);
  }
}
