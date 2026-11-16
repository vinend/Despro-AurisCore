param(
    [Parameter(Mandatory=$true)][ValidateSet('Gateway','Web')][string]$Service,
    [Parameter(Mandatory=$true)][System.Net.IPAddress]$LanAddress
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$web = Join-Path $repo 'WebApp'
$local = Join-Path $repo '.runtime/hardware'
New-Item -ItemType Directory -Path $local -Force | Out-Null
$tokenFile = Join-Path $local 'pairing-token.txt'
if (-not (Test-Path $tokenFile)) {
    $bytes = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    $token = [Convert]::ToBase64String($bytes)
    try {
        $stream = [IO.File]::Open($tokenFile, [IO.FileMode]::CreateNew)
        try { $buffer = [Text.Encoding]::UTF8.GetBytes($token); $stream.Write($buffer, 0, $buffer.Length) } finally { $stream.Dispose() }
    } catch [IO.IOException] { if (-not (Test-Path $tokenFile)) { throw } }
}
$env:AURISCORE_DEVICE_TOKEN = (Get-Content $tokenFile -Raw).Trim()
$env:AURISCORE_GATEWAY_HOST = '0.0.0.0'
$env:AURISCORE_ALLOWED_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000,http://$($LanAddress):3000"
Write-Host "Website http://$($LanAddress):3000"
Write-Host "ESP32 URI ws://$($LanAddress):8082/device"
Write-Host "Browser URI ws://$($LanAddress):8082/browser"
Write-Host "Pairing token tersimpan lokal di $tokenFile"
if ($Service -eq 'Gateway') {
    Set-Location (Join-Path $web 'mini-services/device-gateway')
    & node (Join-Path (Get-Location) 'node_modules/tsx/dist/cli.mjs') index.ts
} else {
    $env:AURISCORE_ALLOWED_DEV_ORIGINS = $LanAddress.ToString()
    $env:AURISCORE_PYTHON = Join-Path $repo 'AI-Pipeline/.runtime/python/python.exe'
    if (-not (Test-Path $env:AURISCORE_PYTHON)) { throw 'Python analisis belum tersedia.' }
    Set-Location $web
    & node node_modules/next/dist/bin/next dev --hostname 0.0.0.0 --port 3000
}
exit $LASTEXITCODE
