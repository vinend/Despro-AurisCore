# ESP32 Wi-Fi streaming setup and implementation state

This adds the v2 device gateway, browser decoder, live listening, sample-clock
recording and WAV download alongside the existing analysis API. The mock remains
available and never substitutes automatically for physical audio. Actual sensor
acquisition is not implemented: no hardware circuit/driver has been supplied.

## Gateway on the laptop

Install dependencies in `WebApp/mini-services/device-gateway`, then configure the
current PowerShell session. Use your own pairing token; never put it in a URL or Git.

```powershell
npm ci
$env:AURISCORE_DEVICE_TOKEN = '<your pairing token, at least 16 characters>'
$env:AURISCORE_GATEWAY_HOST = '0.0.0.0'
$env:AURISCORE_ALLOWED_ORIGINS = 'http://localhost:3000'
npm start
```

Port defaults to 8082; `AURISCORE_GATEWAY_PORT` overrides it. Host defaults to loopback
for tests/local use; LAN device connections require an explicitly reachable bind.
Allow inbound TCP on the configured port for the intended private network only.
Add the exact WebApp origins you use (comma-separated) rather than `*`.
Start Next.js in another terminal using the existing local launch instructions.

On the page, choose **ESP32 melalui Wi-Fi**, enter the browser endpoint (for a
local laptop, `ws://localhost:8082/browser`) and pairing token, then connect.
Credentials stay in component memory; no URL/localStorage persistence. A gateway
connection alone does not enable recording. Firmware authentication + hello +
start acknowledgement + actual valid audio are required.

For an ESP32-hosted AP: join that Wi-Fi network on the laptop; determine the
laptop's actual IP; configure firmware URI `ws://LAPTOP-IP:8082/device`.
The AP's address is not the laptop gateway address. No internet is necessary for
LAN capture/analysis when dependencies/models are already installed.

## Firmware

See [firmware README](../../Firmware/esp32-streaming/README.md). ESP-IDF project
provides AP setup, pairing/authentication, binary PCM publishing, controls, bounded
queues and reconnect. It deliberately has no made-up GPIO/capture driver and emits
no generated audio. An acquisition task must feed real 400-sample PCM blocks at
8 kHz into `auriscore_stream_push` while `auriscore_stream_enabled()` is true.
Until then, the UI reports unavailable/stalled audio rather than successful capture.
ESP-IDF/compiler is not installed in the current workspace: firmware has not been
built or flashed, and the ESP32 Wi-Fi AP has not been physically verified.

## Listening and recording

Click **Dengarkan langsung** to enable AudioWorklet playback; use headphones.
Volume/mute apply to listening only. Listening has a 100 ms initial jitter buffer,
bounded 300 ms backlog and small occupancy-based clock correction. These settings
are engineering defaults, not a measured latency claim. AudioWorklet requires
HTTPS or localhost: plain HTTP at a phone/LAN IP can show waveform/recording but
live listening may be unavailable. Use HTTPS/WSS for that browser deployment.

Recording runs independently of listening and stops after 80,000 received samples.
Silence in delivery, invalid frames, packet loss, acquisition overflow or a device
disconnect prevents a complete recording. Playback/download use the original WAV,
and valid recordings call the existing Heart/Abdomen analysis service. The model
approval requirements are unchanged; streaming does not activate absent models.

## Checks and remaining acceptance

`npm test` in `mini-services/device-gateway` checks real WebSocket pairing/origin,
command routing, exact binary forwarding, invalid continuity and stalled sources.
`npm run test:analysis` in WebApp includes the gateway/browser decoder, full
80,000-sample recording and sample-for-sample WAV checks, listening processor and
recording watchdog. Set `AURISCORE_PYTHON` for Python-dependent tests.
The engineering publisher in tests is explicitly synthetic; it is not device proof.

Physical acceptance still requires the team hardware handoff, acquisition driver,
firmware build/flash, actual chestpiece recording and sustained/latency testing.
See [team handoff](../../HARDWARE_TEAM_HANDOFF.md),
[wire contract](../../DEVICE_STREAMING_PROTOCOL.md) and
[implementation plan](../../DEVICE_STREAMING_PLAN.md).
