# AurisCore WebApp

Next.js prototype for the AurisCore ESP32-S3 digital stethoscope. The live PCG stream and recording classification are still simulated by `mini-services/mock-device`. The separate Heart WAV file simulator now runs the existing CPU-only Python DSP and displays its real `heart-analysis-v1` engineering output. It does not load a Murmur AI model.

## Architecture

```text
[Browser]                        [Development computer]          [Future]
 React (Next.js)  ──WebSocket──►  mock-device   ──replace with──► ESP32-S3
 route / (port 3000)  JSON        (port 8081)                    same protocol
```

- The frontend connects to the mock device through a real WebSocket transport.
- A physical device can be selected with `?device=ws://<device-address>/ws` without changing the client code.
- The protocol uses JSON, epoch-millisecond timestamps, signed int16 mono PCM, 8000 Hz, and 400 samples per 50 ms packet. The 2 kHz figure in the PDS is the upper signal-band frequency, not the sampling rate.
- The protocol reference is [`mini-services/mock-device/README.md`](mini-services/mock-device/README.md).

## Run locally

### Heart WAV file demo (no mock-device required)

From the Windows checkout, keep `AI-Pipeline/.runtime/python/python.exe`
available with NumPy, SciPy, and SoundFile. Create a safe synthetic demo WAV
without using any research split, then start the local Next.js app:

```powershell
cd C:\Life\kuliah\SEMESTER7\Despro-AurisCore
AI-Pipeline\.runtime\python\python.exe AI-Pipeline\scripts\create_synthetic_heart_demo_wav.py --output "$env:TEMP\auriscore-heart-demo.wav"
cd C:\Life\kuliah\SEMESTER7\Despro-AurisCore\WebApp
npm.cmd run dev
```

Open `http://localhost:3000`, scroll to **Analisis WAV jantung**, select a
local mono `.wav` (up to 16 MiB), such as the generated file in `%TEMP%`, and
click **Analisis WAV**. The generator refuses to overwrite an existing file;
use a new output name for another run. The selected file
goes to the same-origin `/api/heart/analyze` route, which runs
`AI-Pipeline/scripts/analyze_heart_wav.py --stdin` in a short-lived CPU Python
process. The browser displays quality, rate/BPM, S1/S2 candidates and
intervals, experimental S3/S4 candidates, and explicit Murmur availability.
The file is not saved as a session. The WebSocket simulator may show
"disconnected" if it is not running; this does not block the file demo.

For another local Python environment, set `AURISCORE_PYTHON` to its absolute
executable path before starting Next.js. `AURISCORE_PIPELINE_DIR` can point to
the Windows `AI-Pipeline` directory when the default sibling location differs.
The route requires a local server and Python installation; it is not offline
browser/mobile inference. Use synthetic or approved development WAVs for demos.
Do not use sealed validation/test recordings.

Focused CPU checks:

```powershell
npm.cmd run test:heart
.\node_modules\.bin\tsc.cmd --noEmit
```

The output is a screening prototype, not a diagnosis. S1/S2 and S3/S4 are
candidate events pending labeled-recording validation. Murmur AI remains
unavailable until a frozen, versioned inference adapter is connected.

### Existing mock-device stream

Install dependencies once in both projects:

```powershell
npm install
cd mini-services/mock-device
npm install
```

Start the mock device in the first terminal:

```powershell
cd WebApp/mini-services/mock-device
npm run dev
```

Start the web application in the second terminal:

```powershell
cd WebApp
npm run dev
```

Open `http://localhost:3000/?device=ws://localhost:8081`.

## Production checks

```powershell
npm run lint
npx tsc --noEmit
npm run build
npm start
```

## Main code

```text
src/app/                         Next.js routes and global styles
src/components/auriscore/        AurisCore status, controls, waveform, and results
src/lib/auriscore/               Protocol, connection, buffer, and simulated classifier
src/hooks/                       PCG stream, recording, mobile, and toast hooks
mini-services/mock-device/       WebSocket PCG device simulator
prisma/                          Local database schema
DECISIONS.md                     Web prototype decision log
```

The prototype is not a medical device. The mock-device recording card still
shows simulated classification; the separate Heart WAV card shows CPU DSP
engineering output. BLE/live audio is not connected to that analysis path.
