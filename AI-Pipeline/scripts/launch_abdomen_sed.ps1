param(
    [string]$Config = "configs/abdomen_sed_residual_se.yaml",
    [string]$Name = "EXP-A102-abdomen-crnn-residual-se"
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
$stdoutPath = Join-Path $runtimePath "$Name.stdout.log"
$stderrPath = Join-Path $runtimePath "$Name.stderr.log"
$scriptPath = Join-Path $PSScriptRoot "train_abdomen_sed.py"

$existing = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -and $_.CommandLine.Contains("train_abdomen_sed.py")
} | Select-Object -First 1

if ($existing) {
    Write-Output "CRNN SED training already running. PID: $($existing.ProcessId)"
    Write-Output "Logs: $stdoutPath ; $stderrPath"
    exit 0
}

$argString = "-u `"$scriptPath`" --config `"$Config`" --name `"$Name`""

$process = Start-Process -FilePath $pythonPath `
    -ArgumentList $argString `
    -WorkingDirectory $pipelineRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath

Write-Output "CRNN SED Training PID: $($process.Id)"
Write-Output "Experiment: $Name"
Write-Output "Config: $Config"
Write-Output "Logs: $stdoutPath ; $stderrPath"
Write-Output "Results: $(Join-Path $pipelineRoot "results\$Name")"
