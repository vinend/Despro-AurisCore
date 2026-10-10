/** Explicit network verification source. This is never a physical stethoscope. */
import { WebSocket } from "ws";
import { encodeAudioFrame } from "../../src/lib/auriscore/device-protocol.ts";
if (!process.argv.includes("--engineering-test")) throw Error("Pass --engineering-test to acknowledge synthetic audio.");
const socket = new WebSocket(process.env.AURISCORE_DEVICE_URL ?? "ws://localhost:8082/device");
const token = process.env.AURISCORE_DEVICE_TOKEN;
if (!token || token.length < 16) throw Error("Set the same local gateway pairing token.");
let timer: ReturnType<typeof setInterval> | null = null;
const streamId = Math.floor(Math.random() * 0xfffffffe) + 1;
socket.on("open", () => socket.send(JSON.stringify({ type: "authenticate", token })));
socket.on("message", raw => {
  const message = JSON.parse(raw.toString());
  if (message.type === "authenticated") socket.send(JSON.stringify({ type: "device_hello", protocol: 2, device: "engineering-publisher",
    fw: "synthetic-test", source: "engineering", streamId, samplingRate: 8000, channels: 1, encoding: "pcm16le" }));
  if (message.type === "command") {
    if (timer) clearInterval(timer);
    socket.send(JSON.stringify({ ...message, type: "command_ack", ok: true }));
    if (message.command !== "start_stream") return;
    let seq = 0;
    timer = setInterval(() => {
      if (socket.readyState !== WebSocket.OPEN || socket.bufferedAmount > 32768) { socket.close(); return; }
      const samples = Int16Array.from({ length: 400 }, (_, i) => {
        const time = (seq * 400 + i) / 8000; let value = 0;
        const beat = Math.floor(time / .8);
        for (let b = beat - 1; b <= beat + 1; b++) for (const [center, amplitude] of [[b * .8 + .4, .4], [b * .8 + .7, .28]])
          value += amplitude * Math.sin(2 * Math.PI * 65 * (time - center)) * Math.exp(-.5 * ((time - center) / .016) ** 2);
        return Math.round(value * 32767);
      });
      socket.send(encodeAudioFrame({ streamId, seq, firstSample: seq * 400, flags: 0, samples })); seq++;
    }, 50);
  }
});
socket.on("error", () => { console.error("Engineering publisher connection failed."); });
socket.on("close", () => { if (timer) clearInterval(timer); console.log("Engineering publisher closed."); });
for (const signal of ["SIGINT", "SIGTERM"] as const) process.once(signal, () => { if (timer) clearInterval(timer); socket.close(); });
