param(
    [ValidateSet('UART','Native')][string]$UsbSerial = 'UART'
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$cli = Join-Path $env:LOCALAPPDATA 'Programs/Arduino IDE/resources/app/lib/backend/resources/arduino-cli.exe'
if (-not (Test-Path $cli)) { throw 'Arduino CLI dari Arduino IDE belum ditemukan.' }
$sketch = Join-Path $repo 'Firmware/serial-capture/auriscore_i2s_capture_2mic_ecg_v4'
$build = Join-Path $repo ".runtime/hardware/build-$UsbSerial"
$cdc = if ($UsbSerial -eq 'Native') { 'cdc' } else { 'default' }
$fqbn = "esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,USBMode=hwcdc,CDCOnBoot=$cdc"
$cores = & $cli core list --format json | ConvertFrom-Json
$platform = $cores.platforms | Where-Object id -eq 'esp32:esp32'
if ($platform.installed_version -ne '3.3.12') { throw 'Paket esp32:esp32 versi 3.3.12 harus terpasang.' }
& $cli compile --fqbn $fqbn --build-path $build $sketch
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Build selesai. Pilihan serial: $UsbSerial. Build ini belum di-upload."
Write-Host "Artefak: $build"
