# Wi-Fi device stream v2

Implemented software contract, 2026-10-10. Physical acquisition/hardware acceptance
are pending. This is separate from the retained mock JSON v1.

ESP32 is a WebSocket client publishing to `/device`. The browser is a WebSocket
client controlling/subscribing to `/browser` on the same device gateway. Wi-Fi AP
ownership is separate from WebSocket server ownership. In ESP32 AP mode, the
laptop joins the AP and hosts the gateway at its reachable network address.

Both roles must first send JSON `{ "type": "authenticate", "token": "..." }`.
Token is a local pairing secret of at least 16 characters, supplied outside Git.
Gateway replies `authenticated`. Browser Origin must match an explicit allowlist.
One publisher and one controlling browser are supported; no patient/audio storage.
Handshake/authentication timeout is five seconds, max frame/control payload 2048
bytes, device message limit 50/sec and browser limit 10/sec. Queues are bounded.
Plain WS is for an isolated development LAN; deploy behind TLS/WSS for protected
networks. Pairing does not by itself encrypt traffic or establish compliance.

Device then sends:

```json
{"type":"device_hello","protocol":2,"device":"AurisCore-ESP32S3","fw":"0.1.0-network","source":"hardware","streamId":123,"samplingRate":8000,"channels":1,"encoding":"pcm16le"}
```

`source` is `hardware` or explicitly `engineering`. Engineering streams are labeled
simulation in the UI; source is a declaration, not cryptographic proof of capture.
Identity is 1-64 ASCII letters/digits/underscore/hyphen; firmware is 1-64 characters.
streamId is nonzero uint32, new on every device WebSocket connection/reboot.
Only the fixed 8 kHz mono PCM16 format is accepted in v2.

The controlling browser sends `{type:"command",id:"unique-id",command:"start_stream"}`
or `stop_stream`. IDs are 1-64 ASCII letters/digits/underscore/hyphen. Device must
send `{type:"command_ack",id,command,ok:true|false}` within three seconds.
No audio is accepted before the start acknowledgement. Browser connection automatically
requests streaming after hello; record/stop-recording controls capture locally and
do not stop listening. Physical firmware does not implement demo `set_bpm` or
`set_mode`; Heart position and organ analysis are separate examination metadata.

## Binary frame: exactly 832 bytes

Header is 32 bytes. All multibyte numbers are little-endian, except magic is the
four literal ASCII bytes `AURI`.

| Offset | Width | Value |
| --- | --- | --- |
| 0 | 4 | ASCII `AURI` |
| 4 | 1 | Protocol 2 |
| 5 | 1 | Flags: bit 0 acquisition overflow; all other bits must be zero |
| 6 | 2 | Header size 32 |
| 8 | 4 | streamId |
| 12 | 4 | Sequence uint32, increments per block, wraps modulo 2^32 |
| 16 | 8 | First-sample index uint64, within JavaScript safe integer range |
| 24 | 4 | Sampling rate 8000 |
| 28 | 2 | Sample count 400 |
| 30 | 1 | Channels 1 |
| 31 | 1 | Encoding 1 = signed PCM16 little-endian |
| 32 | 800 | 400 original PCM samples |

Sequence/sample index begin at zero on start in the provided firmware. A browser
joining an active stream may begin at any sample index. Every subsequent frame
must increment index by 400 and sequence by one. Exact duplicate metadata is ignored;
gaps, out-of-order frames, stream changes, overflow and bad formats invalidate the
stream. Sequence/sample counters are acquisition-based, not send-timer based.
No epoch timestamp is assumed. 20 blocks/sec carry 16,000 PCM bytes/sec plus overhead.

Canonical JS codec: `WebApp/src/lib/auriscore/device-protocol.ts`; C encoder:
`Firmware/esp32-streaming/components/auriscore_stream/auriscore_stream.c`.
Golden first eight bytes: `41 55 52 49 02 00 20 00`.

Gateway sends `device_state` (`offline|ready|streaming|error`) with nullable reason.
`streaming` requires actual valid frames. Start without samples or a two-second
audio stall becomes an error and disconnects the device. Acquisition failures use
`source_error`. Gateway websocket ping/pong detects broken connections; the sample
watchdog also detects a connected but non-producing source. Detached controllers
close their publisher connection so it cannot stream unattended indefinitely.

Browser decoder normalizes frames for existing waveform/capture without resampling
original PCM; unknown signal quality is explicit. Hardware battery/BPM remain null
until actually measured. Live AudioWorklet output resampling/concealment is separate
from recording. Capture ends at 80,000 received samples, with a two-second packet
watchdog and 15-second total watchdog. Manual early stop preserves actual duration.
Saved WAV byte content is original PCM; in-memory history remains bounded.
