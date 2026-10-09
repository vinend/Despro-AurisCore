# Tomorrow: Heart hardware integration at the device

Keep H022 separate. The instructions below use the Windows development checkout on `reconcile/windows-master-20261009`. The current verified device path is **WebSocket mock**, not physical BLE. Confirm the real ESP32 firmware transport and values in [HARDWARE_AUDIO_CONTRACT.md](HARDWARE_AUDIO_CONTRACT.md) before connecting physical hardware.

## 1. Start software

In PowerShell terminal A:

```powershell
cd C:\Life\kuliah\SEMESTER7\Despro-AurisCore\WebApp\mini-services\mock-device
npm.cmd run start
```

In PowerShell terminal B:

```powershell
cd C:\Life\kuliah\SEMESTER7\Despro-AurisCore\WebApp
npm.cmd run dev
```

Open `http://localhost:3000`. The WebApp's local Heart API invokes `AI-Pipeline/scripts/analyze_heart_wav.py --stdin` with CPU-only Python. Its default interpreter is `AI-Pipeline/.runtime/python/python.exe`; if unavailable on another laptop, set `$env:AURISCORE_PYTHON` to an installed Python with the AI-Pipeline DSP dependencies before starting WebApp.

## 2. Verify fallback first

Generate a synthetic engineering WAV in PowerShell terminal C:

```powershell
cd C:\Life\kuliah\SEMESTER7\Despro-AurisCore\AI-Pipeline
& .\.runtime\python\python.exe scripts\create_synthetic_heart_demo_wav.py --output .runtime\heart-demo-tomorrow.wav
```

The script refuses to overwrite an existing file; choose another filename if it already exists. On the page, use **Analisis WAV jantung**. Select `AI-Pipeline\.runtime\heart-demo-tomorrow.wav` and click **Analisis WAV**. Confirm quality/BPM/rhythm/event fields appear or an explicit invalid-quality reason. Murmur may show **Analisis Murmur belum tersedia**. Do not use external validation or sealed recordings.

## 3. Power ESP32 and identify its actual transport

Check its firmware/serial console and note advertised name/address, transport, sampling rate, packet layout, and start/stop behavior. Do **not** assume the mock WebSocket format is BLE. Physical BLE service/characteristic UUIDs, control bytes, byte order, and packet sequence field are **TODO HARDWARE CONFIRMATION**. If firmware instead implements the WebApp's documented WebSocket JSON protocol, find its URL and open `http://localhost:3000/?device=ws://DEVICE_HOST:PORT` (replace with the real values).

## 4. Connect

For mock: the connection badge should turn connected automatically with `mock-device` shown. For matching WebSocket firmware: use the `?device=` override above and verify the `hello` message matches protocol version 1, 8000 Hz, mono. For physical BLE: `BleAudioSource` is an injected software adapter only; there is no browser BLE connect control until the firmware contract is supplied. Record confirmed UUIDs/decoder/control commands in `HARDWARE_AUDIO_CONTRACT.md` and wire a Web Bluetooth transport into that adapter. Do not invent bytes to make the UI appear connected.

## 5. Verify stream

Watch **Fonokardiogram** for a waveform. The existing mock uses 400 signed-int16 samples per 50 ms packet, 8000 Hz mono, and increasing sequence numbers. In the **Analisis rekaman perangkat** panel, expand **Telemetri pengembang** after capture: inspect connection, packets, bytes, missing packets, decoded samples, sample rate, duration, and amplitude min/max. Ten seconds should be about 200 packets/80,000 samples for the mock. A sequence gap invalidates the analysis capture rather than filling it with fabricated silence.

## 6. Capture

Click **Rekam dan analisis Heart** in the stream panel. Wait 10 seconds or click **Hentikan dan analisis Heart**. The panel reports `recording → processing → completed` or an explicit transport/audio/DSP error. The older **Sesi rekaman** card is a separate UI simulator and its classifier output is not the Heart DSP result.

## 7. Run analysis and inspect result

Captured PCM is encoded to mono WAV, posted to `POST /api/heart/analyze`, passed to the CPU Python `HeartAnalysisService`, and returned as `heart-analysis-v1`. Check quality, BPM, rhythm, S1/S2 candidates, systolic/diastolic intervals, S3/S4 candidate status, DSP version, and optional Murmur status. The screening disclaimer must remain visible.

## 8. Troubleshooting

| Symptom | First check |
|---|---|
| Device not found | Verify firmware transport; WebApp currently supports WebSocket URL override, not native BLE discovery. |
| Connect failure | Check mock process/port 8081 or real WebSocket host/port and browser console. |
| Immediate disconnect | Check firmware reset/power and protocol `hello`; WebSocket reconnect is automatic. |
| Zero packets | Verify `pcg_packet` messages arrive; inspect browser Network → WS frames. |
| Packets but zero samples | Validate exactly 400 signed-int16 samples for mock protocol; physical BLE requires confirmed decoder. |
| Incorrect sample rate | Confirm 8000 Hz in mock `hello` and packets; unsupported rates are rejected. |
| Missing/corrupt audio | Check sequence jumps, malformed-packet warnings, amplitude min/max; repeat capture. |
| Silent signal | DSP returns invalid quality; check sensor contact/audio path. |
| Analysis error | Confirm `AI-Pipeline/.runtime/python/python.exe` exists and Python DSP imports; inspect the `/api/heart/analyze` HTTP status. |

## 9. Fallback demo

If hardware fails, leave terminal B/WebApp running. Use **Analisis WAV jantung** with the synthetic file generated in part 2. It exercises the same Python DSP and `heart-analysis-v1` result UI without BLE, hardware, Murmur deployment, or GPU training.
