param(
    [string] $Plan = "configs/heart_cnn_queue.json"
)

$ErrorActionPreference = "Stop"
$pipelineRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPython = Join-Path $pipelineRoot ".venv/Scripts/python.exe"
$runtimePython = Join-Path $pipelineRoot ".runtime/python/python.exe"

if (Test-Path -LiteralPath $venvPython) {
    $pythonPath = $venvPython
} elseif (Test-Path -LiteralPath $runtimePython) {
    $pythonPath = $runtimePython
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonPath = (Get-Command python).Source
} else {
    throw "Python executable was not found. Please activate your virtual environment or install Python."
}
$runtimePath = Join-Path $pipelineRoot ".runtime"
New-Item -ItemType Directory -Path $runtimePath -Force | Out-Null
$stdoutPath = Join-Path $runtimePath "training-queue.stdout.log"
$stderrPath = Join-Path $runtimePath "training-queue.stderr.log"
$scriptPath = Join-Path $PSScriptRoot "run_experiment_queue.py"
$existing = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and $_.CommandLine.Contains("run_experiment_queue.py") -and
    $_.CommandLine.Contains($scriptPath)
} | Select-Object -First 1
if ($existing) {
    Write-Output "Training queue already running. PID: $($existing.ProcessId)"
    Write-Output "Logs: $stdoutPath ; $stderrPath"
    exit 0
}
$process = Start-Process -FilePath $pythonPath `
    -ArgumentList @("-u", "`"$scriptPath`"", "--plan", "`"$Plan`"") `
    -WorkingDirectory $pipelineRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
Write-Output "Training queue PID: $($process.Id)"
Write-Output "Logs: $stdoutPath ; $stderrPath"
Write-Output "Results: $(Join-Path $pipelineRoot 'results')"
