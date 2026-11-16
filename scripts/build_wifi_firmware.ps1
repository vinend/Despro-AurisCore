param([switch]$NativeUsb, [switch]$DisableBrownout)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$cli = Join-Path $env:LOCALAPPDATA 'Programs/Arduino IDE/resources/app/lib/backend/resources/arduino-cli.exe'
$core = (& $cli core list --format json | ConvertFrom-Json).platforms | Where-Object id -eq 'esp32:esp32'
if ($core.installed_version -ne '3.3.12') { throw 'Required: esp32:esp32 3.3.12' }
$build = Join-Path $repo '.runtime/hardware/build-wifi'
$sketch = Join-Path $repo 'Firmware/wifi-capture/auriscore_wifi_capture'
$fqbn = 'esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,USBMode=hwcdc,CDCOnBoot=default'
if ($NativeUsb) {
    $build = Join-Path $repo '.runtime/hardware/build-wifi-native-usb'
    $fqbn = 'esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,USBMode=hwcdc,CDCOnBoot=cdc'
}
$compileArgs = @('compile', '--fqbn', $fqbn)
if ($DisableBrownout) {
    $build += '-brownout-off'
    $compileArgs += @('--build-property', 'compiler.cpp.extra_flags=-DAURISCORE_DISABLE_BROWNOUT=1')
    Write-Warning 'Brownout detector disabled in this firmware. Supply stability and audio integrity require physical verification.'
}
$compileArgs += @('--build-path', $build, $sketch)
& $cli @compileArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Build only; no upload. Firmware artifacts: $build"
