param([string]$Port='COM3',[string]$Ssid,[string]$GatewayHost,
  [ValidateSet('wifi','hotspot')][string]$Kind='wifi',[switch]$Primary,[switch]$SaveOnly)
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $repo
$python=Join-Path $repo 'AI-Pipeline/.runtime/python/python.exe'
Write-Host 'AurisCore: configure ESP32 Wi-Fi locally; password stays out of chat/logs.'
Write-Host "Network: $Ssid | Gateway laptop: $GatewayHost"
$setupArgs=@((Join-Path $repo 'scripts/configure_wifi_capture.py'),'--port',$Port,'--kind',$Kind)
if ($Ssid) { $setupArgs+=@('--ssid',$Ssid) }
if ($GatewayHost) { $setupArgs+=@('--host',$GatewayHost) }
if ($Primary) { $setupArgs+='--primary' }
if ($SaveOnly) { $setupArgs+='--save-only' }
& $python @setupArgs
if ($LASTEXITCODE -eq 0) { Write-Host "Open http://$($GatewayHost):3000 on the phone; pair normally." }
else { Write-Host 'Configuration did not complete. Keep this window open for troubleshooting.' }
