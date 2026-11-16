param(
    [ValidatePattern('^COM[0-9]+$')]
    [string]$Port,
    [switch]$ListPorts,
    [switch]$NativeUsb,
    [switch]$RetryOnce
)

# Standalone Windows PowerShell 5.1 monitor for AurisCore Wi-Fi firmware.
$ErrorActionPreference = 'Stop'
$ports = @([System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object)
if ($ListPorts) { $ports; return }
if (!$Port) {
    Write-Host "Available ports: $($ports -join ', ')"
    if ($ports.Count -eq 1) { $Port = $ports[0] }
    else { $Port = Read-Host 'ESP32 port, for example COM3' }
}
if ($Port -notin $ports) { throw "Port $Port is unavailable. Connect the ESP32 USB data cable." }

$logPath = Join-Path ([IO.Path]::GetTempPath()) ('auriscore-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N') + '.log')
$serial = New-Object System.IO.Ports.SerialPort $Port,115200,None,8,one
$serial.DtrEnable = [bool]$NativeUsb
$serial.RtsEnable = $false
$serial.WriteTimeout = 1000
$identified = $false
$buffer = ''
$nextStatus = [DateTime]::MinValue
$nextRetry = [DateTime]::MinValue
$logWriter = $null
function Write-MonitorLine([string]$Message) {
    $entry = (Get-Date -Format 'HH:mm:ss.fff') + '  ' + $Message
    Write-Host $entry
    if ($null -ne $script:logWriter) {
        try { $script:logWriter.WriteLine($entry) }
        catch {
            Write-Warning 'File logging stopped. Serial monitoring continues in this window.'
            try { $script:logWriter.Dispose() } catch { }
            $script:logWriter = $null
        }
    }
}

try {
    $serial.Open()
    try {
        $logStream = [IO.FileStream]::new($logPath, [IO.FileMode]::CreateNew,
            [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite)
        $logWriter = [IO.StreamWriter]::new($logStream, [Text.UTF8Encoding]::new($false))
        $logWriter.AutoFlush = $true
    } catch {
        Write-Warning 'Could not create the log file. Serial monitoring continues in this window.'
    }
    $host.UI.RawUI.WindowTitle = "AurisCore LIVE - $Port"
    Write-MonitorLine "Listening on $Port. Log: $logPath"
    Write-Host 'R = one Wi-Fi RETRY after identification; S = STATUS; Q = close.'
    while ($true) {
        if (!$identified -and (Get-Date) -ge $nextStatus) {
            $serial.Write("STATUS`n")
            $nextStatus = (Get-Date).AddSeconds(3)
        }
        $buffer += $serial.ReadExisting()
        while ($buffer.Contains("`n")) {
            $end = $buffer.IndexOf("`n")
            $line = $buffer.Substring(0, $end).Trim()
            $buffer = $buffer.Substring($end + 1)
            if ($line -eq 'AURISCORE_WIFI_CAPTURE_V1') { $identified = $true }
            # Only firmware diagnostics are retained. Never log arbitrary payloads.
            if ($line -match 'Brownout detector was triggered') {
                Write-MonitorLine '[ESP32] Brownout detector was triggered'
            } elseif ($line -match '^(AURISCORE_WIFI_CAPTURE_V1|(?:CONFIG|WIFI|I2S|PROFILE|RADIO|GATEWAY|USB|CAPTURE|PROVISION|RUNTIME|BUILD|BROWNOUT)_[A-Za-z0-9_.= -]+)$') {
                Write-MonitorLine "[ESP32] $line"
            } elseif ($line -match '^(rst:|ESP-ROM:)') {
                Write-MonitorLine "[BOOT] $line"
            }
        }
        if ($buffer.Length -gt 4096) { $buffer = '' }
        if ($RetryOnce -and $identified) {
            $RetryOnce = $false
            $nextRetry = (Get-Date).AddSeconds(15)
            Write-MonitorLine '[PC] One requested Wi-Fi RETRY'
            $serial.Write("RETRY`n")
        }
        if ($host.UI.RawUI.KeyAvailable) {
            $key = $host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown').Character
            if ($key -eq 'q') { break }
            if ($key -eq 's') { $serial.Write("STATUS`n") }
            if ($key -eq 'r') {
                if ((Get-Date) -lt $nextRetry) {
                    Write-Host 'Wait 15 seconds between Wi-Fi retries.'
                } elseif ($identified) {
                    $nextRetry = (Get-Date).AddSeconds(15)
                    Write-MonitorLine '[PC] RETRY requested manually'
                    $serial.Write("RETRY`n")
                } else { Write-Host 'Waiting for AurisCore firmware identification.' }
            }
        }
        Start-Sleep -Milliseconds 50
    }
} finally {
    $serial.Dispose()
    if ($null -ne $logWriter) { $logWriter.Dispose() }
    Write-Host "Monitor closed. Log path: $logPath"
}
