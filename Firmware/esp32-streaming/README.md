# ESP32-S3 Wi-Fi streaming transport

ESP-IDF network project with a reusable `auriscore_stream` component. No GPIO
acquisition driver or generated audio source is included. It will connect/register
but cannot produce stethoscope audio until a real capture task is connected.
Source code has not been built/flashed here: no ESP-IDF toolchain or board is available.

In an installed ESP-IDF environment (5.2+; managed WebSocket component resolves
through `idf_component.yml`), from this directory:

```powershell
idf.py set-target esp32s3
idf.py menuconfig
idf.py build
idf.py -p YOUR_COM_PORT flash monitor
```

Configure **AurisCore Wi-Fi network**: AP SSID/password, device ID, gateway URI and
pairing token. The gateway URI is the laptop's IP on the ESP32 AP network, e.g.
`ws://YOUR_LAPTOP_IP:8082/device`; do not use `localhost` or assume the AP's IP is
the laptop's. Password/token have no usable defaults. `sdkconfig*`, build output
and managed components stay ignored because local configuration can contain secrets.
The tracked `sdkconfig.defaults` enables the certificate bundle and contains no secrets.
Validate managed-component/SDK compatibility with a real firmware build before flashing.

`main/main.c` starts an ESP32 access point. To use an existing router, initialize
your STA Wi-Fi connection instead and call the same transport component after
network readiness. In AP mode the component retries its laptop connection as
the laptop joins. WebSocket role is client regardless of AP/STA Wi-Fi role.
TLS uses the IDF certificate bundle for WSS; no certificate verification bypass.

## Connect real acquisition

From your capture task (not interrupt handler):

```c
/* samples contains exactly 400 real signed PCM16 mono samples, at 8000 Hz. */
if (auriscore_stream_enabled()) {
    esp_err_t status = auriscore_stream_push(samples);
    /* Handle non-ESP_OK; a full queue invalidates this stream. Do not hide loss. */
}
```

The transport does not know ADC/I2S pins. Convert raw ADC/I2S words correctly in
the acquisition driver, with hardware-paced sampling and documented gain/DC
handling. `auriscore_stream_push` does not resample, pad or synthesize audio.
It uses an eight-block bounded queue; overflow or old/failed sends emits
`source_error`. Device frames follow [v2 contract](../../DEVICE_STREAMING_PROTOCOL.md).
Gateway start/stop commands are acknowledged before enabling sampling/publishing.
Firmware stream identifier changes on each connection; capture queues reset.

The hardware team must supply the board, acquisition circuit and wiring described
in [HARDWARE_TEAM_HANDOFF.md](../../HARDWARE_TEAM_HANDOFF.md) for the capture driver.
