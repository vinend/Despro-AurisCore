# ESP32 stethoscope streaming implementation plan

Status: proposed, implementation not started. Date: 2026-10-10.

User clarification: integration is through the ESP32 Wi-Fi network. GPIO/pin
mapping is not a prerequisite for implementing the network/streaming layer.
Treat audio acquisition as an upstream PCM source interface; only adapting or
validating that acquisition driver requires circuit details. Network software can
be implemented and tested independently, without claiming simulated input is
actual stethoscope acquisition.

## Goal and repository findings

Stream actual stethoscope samples from the ESP32 over Wi-Fi/WebSocket into the
existing WebApp: live waveform, audible monitoring, capture, WAV playback/download
and the existing Heart/Abdomen analysis service. Continuous transport and listening
are distinct from analysis, which currently runs on completed recordings.

Existing reusable code:

- `WebApp/src/lib/auriscore/pcg-connection.ts`: browser WebSocket connection and
  reconnect, currently JSON only and connected before a verified device handshake.
- `use-pcg-stream.ts`, `ring-buffer.ts`, `pcg-waveform.tsx`: waveform path.
- `heart-audio-source.ts`, `recording-session.ts`: validated PCM capture, WAV
  encoding, real recording lifecycle and fail-safe sequence handling.
- `/api/analysis` and retained Python worker: recorded-audio analysis.
- `mini-services/mock-device`: synthetic source; it is not a physical-device
  ingest service and must remain explicitly labeled as simulation.

The user directs this plan to use the PRD hardware baseline: **ESP32-S3**, nominal
**8000 Hz**, **12-bit ADC target**, and approximately **20-2000 Hz** signal coverage.
The 16-bit PCM transport container does not turn a 12-bit acquisition into 16-bit
measurement precision. No ESP32 source, board pinout or verified sensor acquisition
driver was found in this checkout. Root PRD/architecture specify BLE/native mobile, while
WebApp decisions specify Wi-Fi/WebSocket. The requested Wi-Fi work is the scope of
this plan. Implementation must reconcile those documents explicitly and retain
native/offline goals as separate gaps rather than claim they are satisfied.

## Proposed topology

```text
Stethoscope sensor / analog front end / digital microphone
    -> ESP32 acquisition driver + DMA + bounded sample queue
    -> Wi-Fi WebSocket client
    -> device-gateway mini-service (device ingest + browser subscription)
    -> browser validated PCM dispatcher
        -> live waveform
        -> AudioWorklet listening buffer -> headphones
        -> recording buffer -> WAV playback/download
        -> existing /api/analysis -> Python -> Heart/Abdomen results
```

The ESP32 and browser are both clients of the gateway. The gateway runs alongside
the existing Next.js backend, using the repository's mini-service pattern; the
analysis API and model loading are reused. It does not store raw audio by default.
Prototype deployment supports an ESP32-hosted Wi-Fi access point (laptop/browser
joins the device's network) or a shared router/hotspot, with no cloud required.
Wi-Fi access-point ownership and WebSocket server ownership are independent: if
using the gateway topology on the ESP32 access point, the ESP32 publishes to the
laptop's reachable address on that network. Confirm that address through explicit
configuration/discovery rather than assuming the access point hosts the gateway.
The ESP32 connects to the laptop's reachable LAN address, not `localhost`.
The gateway listening interface/port, allowed origins and device identity are
configurable. HTTPS browser deployments require a compatible WSS endpoint.

Direct browser-to-ESP32 WebSocket serving is an alternative if existing firmware
already implements it. Confirm that firmware before adding a second architecture.
For new firmware, use the gateway topology above for ingest, device presence and
future subscribers. Initial scope is one device and one controlling browser.

## Phase 1 — freeze the Wi-Fi and stream contract

Use ESP32-S3 from the PRD. Define access-point/shared-network setup, endpoint
discovery/configuration, connection roles and the existing firmware framework.
No GPIO assignment is required for this phase. Define an upstream audio-source
interface that supplies real PCM blocks with declared rate/encoding and sample
counters. Sensor/ADC details are needed only if its acquisition driver must also
be implemented or corrected; do not reinterpret unknown ADC values as signed PCM.

Propose a versioned hardware protocol distinct from the mock JSON v1:

- Audio: mono, signed 16-bit little-endian PCM at 8000 samples/second.
- Initial block: 400 samples (50 ms), 800 payload bytes; 20 blocks/second.
- Raw bandwidth: 16,000 bytes/second (128 kbit/s), plus protocol overhead.
- JSON control/handshake; binary audio with a fixed documented header.
- Header includes magic/version, stream identifier, sequence number, first-sample
  index, sample count and flags. Specify exact field widths/order, wrap behavior,
  maximum lengths and whether session/format information is negotiated in hello.
- Use sample indices/device monotonic time for continuity, not browser arrival
  time or an assumed ESP32 epoch clock. Gateway receipt time is separate telemetry.
- Handshake identifies device, firmware, hardware source, capabilities and actual
  sample format; reject incompatible formats before enabling recording.
- Commands: start/stop streaming, acknowledged command IDs, heartbeat and errors.
  Reconnect/device reboot gets a new stream identity; old audio never joins it.
- Heart recording location and Heart/Abdomen analysis mode are separate metadata.
  Do not reuse mitral/aortic/etc. as Abdomen firmware modes.
- Battery, measured rate and quality telemetry are nullable until implemented.
  The physical device does not implement demo `set_bpm` or fabricated BPM.

Binary v2 is a proposed choice to measure and document, not an existing contract.
Retain mock v1 through an explicit adapter; reject unknown hardware versions.

Deliverable: protocol specification/golden frames and network configuration,
updated PRD transport snapshot, ADR, architecture/integration/acquisition docs.

## Phase 2 — implement ESP32 Wi-Fi publishing and the PCM source adapter

Add/adapt `Firmware/` using the actual framework rather than replacing existing
working firmware. First implement Wi-Fi setup, WebSocket connection, handshake,
PCM block publishing, command handling, heartbeat and reconnect behind an
audio-source interface. Connect that interface to the device's existing capture
code without requiring the networking module to know GPIO assignments.

If real acquisition code is absent or incompatible, implement it separately using
the sensor's supported driver and hardware-paced sampling.
Digital I2S input uses DMA; analog input requires its suitable ADC acquisition
driver. Separate capture and network tasks with a bounded queue so sending does
not determine sample timing. Overflow is reported, never silently hidden.

Confirm channel selection, input word width/alignment, ADC offset and full scale,
signed conversion, clipping and gain. Preserve the stethoscope's low-frequency
content; no voice-oriented filtering or undocumented automatic normalization.
If the sensor/driver does not support 8 kHz acquisition directly, acquire at a
supported rate and explicitly filter/resample to the agreed transport rate.
Version the acquisition transformation separately from AI preprocessing.

First verify sensor capture with sample counters and an engineering WAV export;
then add authenticated device registration, binary sends, heartbeat/reconnect and
acknowledged start/stop. Wi-Fi settings/secrets stay outside tracked source.
Network stalls cannot produce unbounded queues or a burst of obsolete live audio.

Deliverable: buildable streaming firmware, network/build/flash guide, PCM-source
adapter and observable overflow/sample counts. Real microphone capture is verified
when the actual device source is connected; a generated test source stays explicitly
labeled engineering-only. A wiring guide is needed only for acquisition-driver work.

## Phase 3 — add the device gateway

Add `WebApp/mini-services/device-gateway/` without changing the mock into a real
device. Use separate device-ingest/browser-subscription paths and validate role,
identity, version, payload length, format and commands. Bind browser subscriptions
to a specific device/stream; do not broadcast recordings across unrelated clients.
Pairing/authentication, origin validation and connection/message limits belong in
the initial design, with secure settings documented for WSS deployment.

Forward validated PCM without changing its values. Track connected versus actively
streaming/stale devices, heartbeat expiry, received samples, malformed frames and
capture/queue overflow. Serialize controlling commands and route acknowledgements.
Bound per-client send queues; disconnect/resynchronize slow clients rather than
accumulate stale audio. Device disconnect invalidates an active browser capture
even when its connection to the gateway remains open.

Deliverable: gateway start/config scripts and ingest/control/reconnect tests.

## Phase 4 — connect physical streaming and live listening in the WebApp

Extend `pcg-connection.ts` and its protocol adapter to decode binary frames,
negotiate readiness and expose device presence/stream errors. A gateway connection
alone must not show an ESP32 as ready. Reset buffers on stream changes/reboots.
Propagate malformed audio and acquisition overflow to recording rather than only
ignore errors. Detect prolonged silence in packet delivery as a transport stall.

Use one validated PCM dispatcher for waveform, listening and recording. Add
explicit hardware/simulator selection and source identity; real-device failure
must never cause automatic substitution with synthetic audio.

Add Web Audio/AudioWorklet listening enabled by a user click, with mute/volume and
a bounded jitter buffer. Resample 8 kHz PCM for the browser output sample rate;
handle clock drift, underruns, tab suspension and reconnect. Any playback concealment
is confined to listening/display; recording retains original samples and gaps.
Use headphones during verification to avoid acoustic feedback into the sensor.
Show unavailable battery/BPM/quality as unavailable rather than mock defaults.

Deliverable: real device waveform and audible stream, explicit ready/stale/error
states, and compatibility tests with the existing simulator.

## Phase 5 — reliable recording and existing analysis integration

Start from the existing ten-second recording controller. Add sample-clock targets
and a separate wall-clock watchdog: 80,000 received samples form ten seconds at
8 kHz, while missing/stalled samples cause an incomplete recording error.
Coordinate stream readiness/start acknowledgements with recording boundaries and
stop acknowledgements with final buffered frames. Retain manual stop/actual duration.

Keep captured samples unchanged for WAV, allow playback/download, and retain device,
stream/format/acquisition provenance in bounded session metadata. A disconnect,
overflow, unexpected format/location change or sample-index gap invalidates capture.
Never fill those gaps to manufacture complete audio for analysis.

Pass valid captures to the existing shared Heart/Abdomen service. Keep inference
off the network receive/audio scheduling path. Streaming continues independently
of model availability. Continuous model inference/rolling classification and durable
patient/session storage are separate extensions, not hidden prerequisites.

Deliverable: actual stethoscope -> playable/exportable WAV -> existing DSP/model
adapter result, including safe quality/missing-model outcomes.

## Phase 6 — software and hardware acceptance

Automated: binary encode/decode golden frames, version/length/range validation,
duplicate/gap/sample-index behavior, role/device isolation, command timeouts,
queue bounds, reconnect/new stream identity, stale-device detection, audio buffer
resampling and unchanged PCM -> WAV -> analysis behavior. Firmware builds on the
confirmed board configuration; protocol fixtures must agree in both environments.

Bench: known tone/pulse capture checks actual sampling rate, amplitude/clipping,
channel/word conversion and packet continuity. Replay generated PCM over the full
firmware/gateway path for byte comparison where a firmware test input is available;
keep this engineering test source explicitly identified. Then test real chestpiece
audio, listening, waveform, recording and exported WAV on desktop/mobile browsers.

Proposed acceptance:

- A ten-second complete capture contains 80,000 samples / 160,000 PCM bytes.
- A ten-minute LAN run has no unexplained missing samples or unbounded memory;
  transport/acquisition overflow and Wi-Fi interruptions are explicitly visible.
- Network disconnect, ESP32 reboot, slow browser and gateway restart all recover;
  the interrupted recording is invalidated and a new recording can succeed.
- Actual playback is audible; exported WAV matches captured PCM and duration.
- Listening latency and jitter are measured. The PRD <100 ms target is not assumed
  achieved; begin with 50 ms packet compatibility and tune buffering/block size
  against measurements if required.
- A physical capture reaches the same Heart/Abdomen API with clear quality or
  missing-model status. Streaming does not authorize unapproved models.

Deliverable: automated results, firmware build evidence, measured hardware report
and a reproducible LAN setup/troubleshooting guide. Physical acceptance requires
the connected board and sensor; software simulation cannot establish it.

## Implementation status (2026-10-10)

Implemented the v2 binary PCM protocol, authenticated device gateway, explicit
browser source selection, waveform/recording integration, live AudioWorklet
listening, WAV export control and software continuity tests. Added an ESP-IDF
network component with an upstream `auriscore_stream_push()` interface and an
ESP32-S3 AP example. The engineering publisher is explicitly synthetic.

The acquisition driver is pending the hardware handoff: exact sensor/ADC and
wiring are not known, and no capture firmware existed. Firmware compilation,
flashing, real chestpiece audio, long LAN runs, latency measurement and physical
acceptance remain pending. Software verification is recorded in `TESTING.md`;
this status does not mark the physical acceptance criteria complete.

## Driver references

- [Espressif ESP32-S3 I2S/DMA documentation](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/i2s.html)
- [Espressif WebSocket client documentation](https://docs.espressif.com/projects/esp-protocols/esp_websocket_client/docs/latest/index.html)

These establish driver capabilities; the specific capture driver and pinned SDK
must match the user's actual hardware and existing framework.
