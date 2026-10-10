# Heart audio acquisition contract (development)

The root [PRD.md](PRD.md) and [INTEGRATION.md](INTEGRATION.md) require a future ESP32-S3 → BLE → mobile path. The current WebApp device implementation instead uses a **WebSocket JSON simulator**; `WebApp/DECISIONS.md` records WiFi/WebSocket for that web prototype. These are different transport decisions. Neither document supplies a verified physical BLE firmware contract. Resolve the product/web transport choice with the team before claiming a physical BLE demo.

| Field | Existing WebSocket mock (verified in code) | Physical BLE firmware |
|---|---|---|
| Service UUID | Not applicable | **TODO HARDWARE CONFIRMATION** |
| Notify characteristic UUID | Not applicable | **TODO HARDWARE CONFIRMATION** |
| Control characteristic UUID | Not applicable | **TODO HARDWARE CONFIRMATION** |
| Direction | Device server → browser for audio/status; browser → server for mock commands | **TODO HARDWARE CONFIRMATION** |
| Transport | WebSocket JSON, default local `ws://localhost:8081` | **TODO HARDWARE CONFIRMATION** |
| Packet size/layout | One JSON `pcg_packet`: `seq`, epoch-ms `ts`, `samplingRate`, `organMode`, `qualityFlag`, `channels`, exactly 400 signed-int16 values in `samples` | **TODO HARDWARE CONFIRMATION** |
| Sample rate/channels | 8000 Hz, mono, 400 samples/50 ms | Nominal 8000 Hz mono in `INTEGRATION.md`; verify firmware |
| Byte order | JSON numbers; no byte endianness | **TODO HARDWARE CONFIRMATION** |
| Sequence | Monotonic `seq`, starts at 0 per mock connection | **TODO HARDWARE CONFIRMATION** |
| Start/stop | WebApp mock continuously streams; UI captures 10 seconds locally | **TODO HARDWARE CONFIRMATION** |
| Disconnect | WebSocket reconnects; active Heart capture fails safely | **TODO HARDWARE CONFIRMATION** |

Source of truth for the **mock only**: `WebApp/mini-services/mock-device/protocol.ts` and its mirror `WebApp/src/lib/auriscore/protocol.ts`. Do not copy this JSON shape into BLE firmware assumptions without confirmation.

## Software boundary now available

`PcgCaptureBuffer` accepts validated PCM packets, rejects gaps instead of inventing silent samples for analysis, buffers signed int16 mono, and returns `AnalysisReadyAudio` with waveform, sample rate, and telemetry. `pcmToWavFile` packages it as standard mono PCM WAV. Both WAV file input and captured PCM call the same `HeartAnalysisService` and produce `heart-analysis-v1`.

`BleAudioSource` provides connect/disconnect/start/stop/state/error and accepts an **injected firmware-specific transport plus packet decoder**. It cannot connect to a physical device until the UUIDs, notification layout, sample encoding/endianness, and start/stop commands above are confirmed and implemented. Its fake-transport unit test is a software boundary test, not hardware validation. The current WebApp UI captures the existing WebSocket/mock stream only; a physical BLE connection control is pending the firmware contract.

Murmur AI is optional. The Python Heart DSP route currently returns `murmur.status: unavailable`; the rhythm and cardiac-event branches remain usable. Invalid audio returns explicit quality failure instead of invented BPM/events. These are prototype screening outputs requiring validation.

## Current Wi-Fi implementation

The user selects Wi-Fi for the WebApp; v2 device-gateway transport and browser
integration are now implemented. This supersedes the mock-only WebSocket status
above, without claiming BLE implementation. Pin mapping is outside the network
module. See DEVICE_STREAMING_PROTOCOL.md, HARDWARE_TEAM_HANDOFF.md and
WebApp/docs/device-streaming.md. Actual capture/firmware/bench acceptance is pending.
