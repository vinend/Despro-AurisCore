param([switch]$NativeUsb, [switch]$DisableBrownout, [string]$CloudRootCa)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$cli = Join-Path $env:LOCALAPPDATA 'Programs/Arduino IDE/resources/app/lib/backend/resources/arduino-cli.exe'
if (!(Test-Path -LiteralPath $cli)) { $cli = (Get-Command arduino-cli -ErrorAction Stop).Source }
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
if ($CloudRootCa) {
    $pem = (Get-Content -LiteralPath $CloudRootCa -Raw).Trim()
    if ($pem -notmatch '\A(?:-----BEGIN CERTIFICATE-----\r?\n[A-Za-z0-9+/=\r\n]+-----END CERTIFICATE-----\s*)+\z') {
        throw 'CloudRootCa must contain one or more PEM certificates.'
    }
    $stagedSketch = Join-Path $repo '.runtime/hardware/cloud-sketch/auriscore_wifi_capture'
    New-Item -ItemType Directory -Force -Path $stagedSketch | Out-Null
    Copy-Item -Path (Join-Path $sketch '*') -Destination $stagedSketch
    @"
#pragma once
static const char AURISCORE_CLOUD_ROOT_CA[] = R"PEM($pem
)PEM";
"@ | Set-Content -LiteralPath (Join-Path $stagedSketch 'cloud_root_ca.h') -Encoding ascii
    $sketch = $stagedSketch
    $build += '-cloud'
}
$compileArgs += @('--build-path', $build, $sketch)
& $cli @compileArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Build only; no upload. Firmware artifacts: $build"
