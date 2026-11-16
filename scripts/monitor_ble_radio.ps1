param([ValidatePattern('^COM[0-9]+$')][string]$Port = 'COM3')
$ErrorActionPreference = 'Stop'
$serial = New-Object IO.Ports.SerialPort $Port,115200,None,8,one
$serial.DtrEnable = $false
$serial.RtsEnable = $false
$serial.WriteTimeout = 500
$logPath = Join-Path $env:TEMP ('ble-manual-' + (Get-Date -Format yyyyMMdd-HHmmss) + '-' + [guid]::NewGuid().ToString('N') + '.log')
$writer = $null
$identified = $false
$buffer = ''
$trial = 0
$trialClock = $null
$nextStatus = [DateTime]::MinValue
function Write-Entry([string]$Message) {
    $entry = (Get-Date -Format HH:mm:ss.fff) + '  ' + $Message
    Write-Host $entry
    if ($null -ne $script:writer) {
        try { $script:writer.WriteLine($entry) }
        catch {
            Write-Warning 'File logging stopped. Serial output remains visible.'
            try { $script:writer.Dispose() } catch { }
            $script:writer = $null
        }
    }
}
try {
    $serial.Open()
    $file = [IO.FileStream]::new($logPath, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite)
    $writer = [IO.StreamWriter]::new($file, [Text.UTF8Encoding]::new($false))
    $writer.AutoFlush = $true
    $host.UI.RawUI.WindowTitle = "BLE MANUAL R - $Port"
    Write-Host 'R = mulai BLE sekali; S = status; Q = tutup monitor.'
    Write-Host 'Radio menunggu R setelah boot/reset. Brownout dimatikan pada firmware tes ini.'
    Write-Host 'Log mencatat waktu penerimaan serial. Tegangan 3,3 V/EN harus diukur dengan alat ukur.'
    Write-Host 'R+... ms menunjukkan waktu di komputer sejak perintah R dikirim.'
    Write-Host "Log tersimpan di $logPath"
    while ($true) {
        if (!$identified -and (Get-Date) -ge $nextStatus) {
            $serial.Write("s`n")
            $nextStatus = (Get-Date).AddSeconds(2)
        }
        $buffer += $serial.ReadExisting()
        while ($buffer.Contains("`n")) {
            $end = $buffer.IndexOf("`n")
            $line = $buffer.Substring(0, $end).Trim()
            $buffer = $buffer.Substring($end + 1)
            if ($line -match '^(rst:|ESP-ROM:)') { $identified = $false }
            if ($line -match '^STANDALONE_BLE_RADIO_TEST_V2_MANUAL') { $identified = $true }
            if ($line -match '^(STANDALONE_BLE|BROWNOUT_|CPU_MHZ=|RADIO_|TRIAL_|BLE_|rst:|ESP-ROM:|Guru Meditation|Backtrace:)') {
                $elapsed = ''
                if ($null -ne $trialClock) { $elapsed = "[R+$($trialClock.ElapsedMilliseconds) ms] " }
                Write-Entry "[ESP32] $elapsed$line"
            }
        }
        if ($buffer.Length -gt 4096) { $buffer = '' }
        if ($host.UI.RawUI.KeyAvailable) {
            $key = $host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown').Character
            if ($key -eq 'q') { break }
            if ($key -eq 's') { $serial.Write("s`n") }
            if ($key -eq 'r') {
                if ($identified) {
                    $trial++
                    $trialClock = [Diagnostics.Stopwatch]::StartNew()
                    Write-Entry "[PC] REQUEST_ID=$trial REQUEST_R"
                    $serial.Write("r`n")
                } else { Write-Host 'Menunggu identitas firmware BLE manual.' }
            }
        }
        Start-Sleep -Milliseconds 50
    }
} finally {
    $serial.Dispose()
    if ($null -ne $writer) { $writer.Dispose() }
    Write-Host "Monitor ditutup. Log di $logPath"
}
