param([string]$LanAddress, [switch]$OpenBrowser)
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
if (!$LanAddress) {
    $profiles=@(Get-NetConnectionProfile | Where-Object { $_.IPv4Connectivity -ne 'Disconnected' })
    foreach($profile in $profiles) {
        $address=Get-NetIPAddress -InterfaceIndex $profile.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -notmatch '^(127\.|169\.254\.)' } | Select-Object -First 1
        if($address) { $LanAddress=$address.IPAddress; break }
    }
}
$parsed=$null
if(![Net.IPAddress]::TryParse($LanAddress,[ref]$parsed) -or $parsed.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) {
    throw 'Alamat LAN tidak ditemukan. Sambungkan laptop ke Wi-Fi/router atau hotspot HP.'
}
$local=Join-Path $repo '.runtime/hardware'
$logs=Join-Path $local ('launch-'+(Get-Date -Format yyyyMMdd-HHmmss)+'-'+[guid]::NewGuid().ToString('N').Substring(0,6))
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$launcher=Join-Path $PSScriptRoot 'start_hardware_lan.ps1'
function Test-Service([string]$Kind) {
    $uri=if($Kind -eq 'Gateway'){'http://127.0.0.1:8082'}else{'http://127.0.0.1:3000'}
    try {
        $response=Invoke-WebRequest -UseBasicParsing -Uri $uri -TimeoutSec 3
        if($Kind -eq 'Gateway') { return ($response.Content | ConvertFrom-Json).service -eq 'auriscore-device-gateway' }
        return $response.StatusCode -eq 200 -and $response.Content -match 'AurisCore'
    } catch { return $false }
}
foreach($kind in @('Gateway','Web')) {
    if(Test-Service $kind) { Write-Host "$kind sudah aktif."; continue }
    $port=if($kind -eq 'Gateway'){8082}else{3000}
    if(Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) { throw "Port $port sedang dipakai layanan lain. Tidak dihentikan otomatis." }
    $process=Start-Process powershell.exe -WindowStyle Hidden -PassThru -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$launcher,'-Service',$kind,'-LanAddress',$LanAddress) `
        -RedirectStandardOutput (Join-Path $logs ($kind+'.log')) -RedirectStandardError (Join-Path $logs ($kind+'.error.log'))
    $deadline=(Get-Date).AddSeconds(30)
    while(!(Test-Service $kind)) {
        if($process.HasExited -or (Get-Date) -gt $deadline) {throw "$kind belum siap. Periksa log privat di $logs"}
        Start-Sleep -Milliseconds 250
    }
}
$url="http://$($LanAddress):3000/"
Write-Host "Website utama AurisCore: $url"
Write-Host "Gateway: ws://$($LanAddress):8082/browser"
Write-Host 'HP harus dapat menjangkau laptop pada jaringan pilihan. Tidak ada konfigurasi Wi-Fi alat lewat prompt laptop pada pemakaian biasa.'
Write-Host ('Kode pairing: '+(Get-Content -LiteralPath (Join-Path $local 'pairing-token.txt') -Raw).Trim())
Write-Host 'Pasang/lepas kabel mic saat daya alat mati. Sambungan fisik dan hasil pada alat tetap perlu diverifikasi.'
if($OpenBrowser) { Start-Process $url }
