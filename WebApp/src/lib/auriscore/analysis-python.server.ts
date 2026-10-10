/** One retained JSONL Python worker per Node process, with serialized bounded work. */
import { spawn, execFile, type ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { parseOrganAnalysisResult, type AnalysisMode, type OrganAnalysisResult } from "./analysis-result.ts";

export class AnalysisPythonError extends Error {
  constructor(message: string, readonly httpStatus: number) { super(message); }
}
type Pending = { id: string; mode: AnalysisMode; resolve: (result: OrganAnalysisResult) => void;
  reject: (error: Error) => void; cleanup: () => void };
export class AnalysisPythonWorker {
  private child: ChildProcessWithoutNullStreams | null = null;
  private pending: Pending | null = null;
  private output = "";
  private tail: Promise<unknown> = Promise.resolve();
  private queued = 0;
  private idle: ReturnType<typeof setTimeout> | null = null;
  private closed = false;
  private terminations = new Set<Promise<void>>();
  constructor(private readonly python: string, private readonly script: string,
    private readonly env: NodeJS.ProcessEnv = process.env, private readonly timeoutMs = 90_000,
    private readonly maxQueue = 8, private readonly idleMs = 300_000) {}
  analyze(wav: Buffer, mode: AnalysisMode, signal?: AbortSignal): Promise<OrganAnalysisResult> {
    if (this.closed) return Promise.reject(new AnalysisPythonError("Layanan analisis sudah ditutup.", 503));
    if (this.queued >= this.maxQueue) return Promise.reject(new AnalysisPythonError("Layanan analisis sibuk. Coba lagi.", 503));
    this.queued++;
    const deadline = Date.now() + this.timeoutMs;
    const task = this.tail.then(() => this.send(wav, mode, deadline, signal));
    this.tail = task.catch(() => undefined);
    return task.finally(() => { this.queued--; });
  }
  private fail(error: Error, terminate = true) {
    const child = this.child;
    this.child = null;
    this.output = "";
    const pending = this.pending;
    this.pending = null;
    pending?.cleanup();
    pending?.reject(error);
    if (child && terminate) {
      // Windows venv launchers may spawn a second Python process. Kill this tree.
      const termination = new Promise<void>(resolve => {
        if (process.platform === "win32" && child.pid) {
          execFile(path.join(process.env.SystemRoot ?? "C:\\Windows", "System32", "taskkill.exe"),
            ["/PID", String(child.pid), "/T", "/F"], { windowsHide: true, timeout: 5000 }, () => resolve());
        } else { child.once("close", () => resolve()); child.kill(); }
      });
      this.terminations.add(termination);
      void termination.then(() => this.terminations.delete(termination));
    }
  }
  private start() {
    if (this.child) return;
    if (!existsSync(this.python) || !existsSync(this.script))
      throw new AnalysisPythonError("Layanan Python lokal belum dikonfigurasi.", 503);
    const child = spawn(this.python, [this.script, "--serve"], { cwd: path.dirname(path.dirname(this.script)),
      windowsHide: true, stdio: ["pipe", "pipe", "pipe"],
      env: { ...this.env, CUDA_VISIBLE_DEVICES: "-1", TF_CPP_MIN_LOG_LEVEL: "3", PYTHONUNBUFFERED: "1" } });
    this.child = child;
    child.stdout.setEncoding("utf8");
    child.stderr.resume();
    child.stdout.on("data", (part: string) => {
      if (this.child !== child) return;
      this.output += part;
      if (Buffer.byteLength(this.output) > 4 * 1024 * 1024) {
        this.fail(new AnalysisPythonError("Hasil analisis terlalu besar.", 502)); return;
      }
      const newline = this.output.indexOf("\n");
      if (newline < 0) return;
      const line = this.output.slice(0, newline);
      this.output = this.output.slice(newline + 1);
      const pending = this.pending;
      try {
        if (!pending || this.output.trim()) throw new Error("Unexpected worker response");
        const result = parseOrganAnalysisResult(JSON.parse(line), pending.mode);
        if (result.request_id !== pending.id) throw new Error("Worker response mismatch");
        this.pending = null;
        pending.cleanup();
        pending.resolve(result);
        this.idle = setTimeout(() => { this.idle = null; if (!this.pending) this.fail(new Error("Idle worker closed")); }, this.idleMs);
        this.idle.unref();
      } catch { this.fail(new AnalysisPythonError("Respons layanan analisis tidak valid.", 502)); }
    });
    child.on("error", () => { if (this.child === child) this.fail(new AnalysisPythonError("Layanan analisis tidak dapat dimulai.", 503)); });
    child.on("close", () => { if (this.child === child) this.fail(new AnalysisPythonError("Layanan atau paket model analisis belum tersedia.", 503), false); });
    child.stdin.on("error", () => { if (this.child === child) this.fail(new AnalysisPythonError("Layanan analisis terputus.", 503)); });
  }
  private send(wav: Buffer, mode: AnalysisMode, deadline: number, signal?: AbortSignal): Promise<OrganAnalysisResult> {
    if (this.closed) throw new AnalysisPythonError("Layanan analisis sudah ditutup.", 503);
    if (signal?.aborted) throw new AnalysisPythonError("Analisis dibatalkan.", 499);
    const remaining = deadline - Date.now();
    if (remaining <= 0) throw new AnalysisPythonError("Waktu tunggu analisis habis. Coba lagi.", 504);
    if (this.idle) { clearTimeout(this.idle); this.idle = null; }
    this.start();
    return new Promise((resolve, reject) => {
      const id = randomUUID();
      const timer = setTimeout(() => this.fail(new AnalysisPythonError("Waktu tunggu analisis habis. Coba lagi.", 504)), remaining);
      const abort = () => this.fail(new AnalysisPythonError("Analisis dibatalkan.", 499));
      signal?.addEventListener("abort", abort, { once: true });
      this.pending = { id, mode, resolve, reject, cleanup: () => { clearTimeout(timer); signal?.removeEventListener("abort", abort); } };
      this.child!.stdin.write(JSON.stringify({ request_id: id, mode, wav_base64: wav.toString("base64") }) + "\n");
    });
  }
  async dispose() {
    this.closed = true;
    if (this.idle) clearTimeout(this.idle);
    this.fail(new AnalysisPythonError("Layanan analisis ditutup.", 503));
    await Promise.all(this.terminations);
  }
}
const globals = globalThis as typeof globalThis & { auriscoreWorker?: { key: string; worker: AnalysisPythonWorker } };
export function getAnalysisWorker(): AnalysisPythonWorker {
  const pipeline = process.env.AURISCORE_PIPELINE_DIR ? path.resolve(process.env.AURISCORE_PIPELINE_DIR)
    : path.resolve(process.cwd(), "..", "AI-Pipeline");
  const python = process.env.AURISCORE_PYTHON ? path.resolve(process.env.AURISCORE_PYTHON)
    : path.join(pipeline, ".runtime", "python", "python.exe");
  const script = path.join(pipeline, "scripts", "analyze_recording.py");
  const key = JSON.stringify([pipeline, python, process.env.AURISCORE_HEART_PACKAGE ?? null, process.env.AURISCORE_ABDOMEN_PACKAGE ?? null, process.env.AURISCORE_LUNG_PACKAGE ?? null]);
  if (globals.auriscoreWorker?.key !== key) {
    void globals.auriscoreWorker?.worker.dispose();
    globals.auriscoreWorker = { key, worker: new AnalysisPythonWorker(python, script, { ...process.env }) };
  }
  return globals.auriscoreWorker!.worker;
}
