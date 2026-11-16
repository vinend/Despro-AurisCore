# Local Wi-Fi capture prototype — 2026-11-14

## User-selected brownout-off bench build

The user explicitly selected a persistent brownout-detector bypass on 2026-11-14.
Build with `scripts/build_wifi_firmware.ps1 -DisableBrownout`. This writes a
separate `build-wifi-brownout-off` directory (or native-USB counterpart).
It calls ESP-IDF 5.5.5 `esp_brownout_disable()` at setup and prints
`BROWNOUT_DETECTOR_DISABLED` on boot. Each reboot reapplies the bypass until a
protected firmware is flashed. A plain build retains the protected configuration.
The 10 dBm startup-table experiment is separate and is not part of this build.
No successful radio connection or valid audio follows merely from disabling
the detector. Voltage dips can still cause hangs, resets or corrupted data.
Use this build for powered bench testing. Supply/recording acceptance is pending.
Earlier protected-build observations below remain historical evidence.

Combined bench comparison: `.runtime/hardware/phy-startup-10dbm-brownout-off/`
retains a separate verified ELF/image and build script derived from the current
brownout-off UART build. Exactly 14 PHY init power-table bytes are capped at 40
quarter-dBm units (10 dBm) using the installed ESP-IDF 5.5.5 S3 table layout.
The image checksum, ELF digest and image hash are regenerated with esptool.
Brownout-disable setup and other code are identical to the comparison baseline.
This local experimental image requires its own retained build artifacts. A plain
`-DisableBrownout` compilation alone does not apply the PHY-table cap.

## Latest v0.2 engineering status

Both router Wi-Fi and phone hotspot are required. Firmware stores up to four
arbitrary profiles, upserts by SSID, retains fallback entries and rotates every
15 seconds when association fails. A working connection is not interrupted just
because another profile is higher priority. On loss, the connection is invalidated
and new PCM starts with a fresh stream session; no zero padding hides lost audio.
NVS readback is checked before printing successful storage. Existing single-profile
settings remain readable. Current board reports **one saved profile**, not two
verified networks. Do not claim either radio path works until actual acceptance.

Provision a primary router profile with the local interactive password prompt:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/configure_wifi_capture.ps1 -Kind wifi -Primary -SaveOnly
```

Provide its SSID and the gateway laptop host reachable on THAT network. Add/update
the phone-hotspot profile similarly with `-Kind hotspot -SaveOnly`. Neither command
erases the other profile. Passwords remain local and are not echoed/logged.
For a local server, the laptop must join the selected network and its IP/origin
configuration must match; automatic ESP32 fallback cannot move the laptop to a
different LAN. An eventual fixed hosted domain avoids that local-IP requirement.

Startup leaves a five-second USB configuration window before Wi-Fi starts. A
brownout reset enters radio recovery hold. `STATUS` reports profile count/hold;
`RETRY` requests one radio start. Recovery hold prevents another radio attempt
but is NOT a brownout repair and does not enable streaming.

On-board `SELFTEST` temporarily uses generated profiles in RAM, then restores the
real profile state, without writing NVS. It passes actual profile update/priority/
capacity logic and association fallback timer/index checks, including clock wrap.
Packet encoding and FIR outputs match independent Python references exactly on
synthetic inputs (FNV-1a frame 1E275B76, FIR B0C7813). Eleven provisioning tests pass.
Firmware compiles/uploads with flash hash verification. These checks do not prove
two real networks have connected or that real microphone audio crosses Wi-Fi.

### User-supplied deep-sleep example assessment

The screenshots address reconnecting after deep sleep. This firmware does not
enter deep sleep while streaming. Delayed radio startup and deferring I2S until
association are applied. A single radio retry after recovery STILL triggers
brownout at `WIFI_INIT_BEGIN`, before `WIFI_MODE_READY` and I2S. Evidence:
`.runtime/hardware/wifi-delayed-radio-check.json` and `wifi-multiprofile-selftest.json`.
Thus the supplied startup advice has not eliminated this board's observed voltage
drop; deep sleep would additionally stop the required continuous connection.
Brownout protection remains enabled. Hardware power/rail measurement is the next
required independent check; cable/USB/regulator attribution remains unproven.

Older chronological bring-up notes follow; latest status above takes precedence.

ESP32-S3-WROOM-1 N16R8, Arduino ESP32 core 3.3.12, WebSockets library 2.7.2.
This separate sketch preserves the original serial-v4 firmware and GPIO wiring.
It is not flashed automatically by the build script.

Flow: two INMP441 I2S slots at 16 kHz -> organ slot 0 -> original 127-tap FIR
(3600 Hz Kaiser 8.6) -> decimate to 8 kHz -> v2 400-sample PCM frames -> **local**
gateway. Noise slot is acquired but not used for ANC. ECG/buzzer synchronization
is NOT forwarded in this audio-only Wi-Fi prototype; keep serial-v4 for that work.
No mock audio or gap filling. Acquisition runs independently from networking;
queue overflow, DMA errors, partial reads, send failure or >250 ms queue age
invalidate streaming. Real hardware continuity/latency acceptance is still required.

## Wi-Fi and cellular are alternative internet paths

No SSID or password is hard-coded. Any reachable WPA2-compatible **2.4 GHz** Wi-Fi
or phone hotspot may be provisioned. Credentials and gateway host persist in NVS;
the board attempts reconnect after power-up. USB is used for power and one-time
engineering setup, not audio transport in this sketch. NVS secrets are NOT
encrypted by this prototype. Do not present it as a finished consumer setup flow.

- Normal Wi-Fi: ESP32 -> router -> local gateway laptop -> website phone.
- Phone hotspot: enable cellular + 2.4 GHz hotspot; laptop and ESP32 join that
  hotspot for LOCAL testing. Gateway address may change: provision its new IP.
- Bluetooth is not involved in either path. BLE -> native-phone-app -> cellular
  is a separate, unimplemented application path.
- This sketch uses local `ws://HOST:8082/device`. Future internet hosting requires
  a separately verified WSS configuration; do not publish plain WS to the internet.

## Engineering test sequence

1. Run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_wifi_firmware.ps1`.
2. Ensure no recording is active. Stop the serial bridge / close any serial monitor
   so COM3 is free. The gateway permits only ONE publisher: USB bridge and Wi-Fi
   firmware must not compete. Keep local web/gateway services running.
3. Upload the built sketch using the existing Arduino CLI, FQBN:
   `esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,USBMode=hwcdc,CDCOnBoot=default`.
   Upload command (repository root):

```powershell
& "$env:LOCALAPPDATA/Programs/Arduino IDE/resources/app/lib/backend/resources/arduino-cli.exe" upload --port COM3 --fqbn esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,USBMode=hwcdc,CDCOnBoot=default --input-dir .runtime/hardware/build-wifi Firmware/wifi-capture/auriscore_wifi_capture
AI-Pipeline/.runtime/python/python.exe scripts/configure_wifi_capture.py --port COM3
```

4. Enter SSID, hidden password and the gateway laptop's reachable IPv4 address in
   the local terminal. No password/token is printed or copied into sketch source.
   Provisioning refuses to send credentials unless the Wi-Fi firmware identifies
   itself. Firmware reboots and should print `WIFI_IP=...` then
   `GATEWAY_AUTHENTICATED`. Authentication alone does not prove microphone audio.
5. In the website use the same browser gateway/pairing code as before. Confirm
   device `ESP32S3-INMP441-WIFI`, actual waveform, sample continuity, a complete
   recording, disconnect/reconnect and five-minute sustained transport. USB may
   remain attached for POWER. Do not run the USB audio bridge.

## Rollback

Use `scripts/build_serial_firmware.ps1`, then Arduino CLI upload with the same
FQBN/COM3 and `--input-dir .runtime/hardware/build-UART` pointing at
`Firmware/serial-capture/auriscore_i2s_capture_2mic_ecg_v4`. Restart the original
serial bridge. No dataset, source model, threshold or deployed model is altered.

Status on 2026-11-14: compiled successfully (1,104,975 bytes program; 47,388 bytes
globals), uploaded to the identified ESP32-S3 on COM3, esptool flash hashes verified.
The running board answered `AURISCORE_WIFI_CAPTURE_V1` over USB. Network credentials
and end-to-end Wi-Fi audio acceptance are still pending local password entry.
Hotspot-selected test network is configuration only, not compiled into firmware.
No claim of Bluetooth or battery-powered operation.

## Current physical blocker: power brownout

After successful credential storage, the board repeatedly boots and USB diagnostics
explicitly report `E BOD: Brownout detector was triggered`. Configured credentials
are retained; no gateway device connection exists. This is evidence of a supply
voltage drop, not evidence that the hotspot password is wrong. Cable/USB source/
regulator attribution remains unmeasured. The power detector remains enabled.
Next acceptance step is a known-good USB cable and direct powered laptop port
(one power source), followed by boot diagnostics and actual Wi-Fi registration.
No Wi-Fi audio success has been claimed. The provisioning CLI now reports
brownout and repeated boots explicitly instead of a generic 45-second timeout.

Follow-up after user replaced USB cable/port: a 12-second capture still reports
16 brownout messages and 27 boot markers. One bounded startup-isolation change
defers I2S/capture-task initialization until Wi-Fi has connected, with explicit
phase markers. It compiles and flashes successfully with hashes verified.
In an eight-second probe: 16 brownouts, 19 boot markers, `WIFI_INIT_BEGIN` seen,
`WIFI_MODE_READY`, `WIFI_CONNECTING` and `I2S_INIT_BEGIN` never reached. Thus the
failure occurs during `WiFi.mode(WIFI_STA)` before audio capture, association,
gateway authentication or model inference. Evidence:
`.runtime/hardware/wifi-after-cable.json` and `wifi-startup-isolation.json`.
This does not identify which physical supply component drops voltage. Next:
identify whether USB power enters the board directly or via the custom PCB;
replace the USB power source with a known-good source via the same approved USB
input, or have the hardware team measure the module supply during radio startup.
No brownout detector, certificate check, model gate or audio continuity rule is bypassed.
# Portable serial monitor

RGB status support is prepared in `status_led.h`. Physical output defaults to
disabled (`AURISCORE_RGB_DATA_PIN=-1`) because the team has not installed the LED.
Only after confirming an addressable RGB LED and wiring may that pin be assigned.
The website sends organ and recording state through the authenticated gateway
when firmware advertises `indicatorProtocol:1`. SELFTEST checks the actual LED
state engine without touching pins. Processing/errors never signal completion.

An isolated, user-requested brownout-disabled diagnostic was run on native USB.
USB communication failed during Wi-Fi initialization; no stable operation was
established. The protected native-USB image was restored and flash verified.
Evidence remains local in `.runtime/hardware/brownout-off-diagnostic/result.json`.
The diagnostic source was isolated under .runtime, not added to the normal build.

For the ESP32 native USB connector (VID 303A / PID 1001), build with
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/build_wifi_firmware.ps1 -NativeUsb`.
This enables hardware USB CDC on boot and writes a separate
`.runtime/hardware/build-wifi-native-usb` directory. Use the same FQBN with
`CDCOnBoot=cdc` when uploading that build. Then run the portable monitor with
`-Port COM4 -NativeUsb` (replace COM4 with the actual enumerated port).
The default build continues to use the CH343 UART connector. Native USB may
disappear during resets; a missing log does not establish brownout recovery.

Copy `scripts/monitor_auriscore.ps1` to another Windows laptop and connect the
already-flashed ESP32 using a USB data cable. No Python, Arduino IDE, repository,
or credentials are required by the monitor. Run
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\monitor_auriscore.ps1`.
Choose the ESP32 COM port when prompted. Close other serial monitors first.
After firmware identification, R sends one RETRY, S requests STATUS, and Q closes
the port. Diagnostic logs are saved under the Windows temporary directory.
The monitor never starts automatic radio retries. Gateway connectivity still
requires the stored network and gateway address to be reachable. For a power
comparison, retain the same board, cable and peripherals and change the laptop.
