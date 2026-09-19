# AurisCore WebApp

Next.js prototype for the AurisCore ESP32-S3 digital stethoscope. PCG data and classification results are currently simulated by `mini-services/mock-device`; they do not come from physical hardware or the trained AI pipeline.

## Architecture

```text
[Browser]                        [Development computer]          [Future]
 React (Next.js)  ──WebSocket──►  mock-device   ──replace with──► ESP32-S3
 route / (port 3000)  JSON        (port 8081)                    same protocol
```

- The frontend connects to the mock device through a real WebSocket transport.
- A physical device can be selected with `?device=ws://<device-address>/ws` without changing the client code.
- The protocol uses JSON, epoch-millisecond timestamps, signed int16 mono PCM, 2000 Hz, and 100 samples per 50 ms packet.
- The protocol reference is [`mini-services/mock-device/README.md`](mini-services/mock-device/README.md).

## Run locally

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

The prototype is not a medical device. Every classification shown by the current WebApp is explicitly simulated.
