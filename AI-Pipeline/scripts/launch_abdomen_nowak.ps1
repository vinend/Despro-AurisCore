param(
    [string]$Config = "configs/abdomen_sed_nowak.yaml",
    [string]$Name = "EXP-A104-abdomen-crnn-nowak"
)

$ErrorActionPreference = "Stop"
$pipelineRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPython = Join-Path $pipelineRoot ".venv/Scripts/python.exe"
$repoRootVenv = Join-Path (Resolve-Path (Join-Path $pipelineRoot "..")).Path ".venv/Scripts/python.exe"
$systemPython = "python"

if (Test-Path -LiteralPath $venvPython) {
    $pythonPath = $venvPython
} elseif (Test-Path -LiteralPath $repoRootVenv) {
    $pythonPath = $repoRootVenv
} else {
    $pythonPath = $systemPython
}

$runtimePath = Join-Path $pipelineRoot ".runtime"
New-Item -ItemType Directory -Path $runtimePath -Force | Out-Null
$stdoutPath = Join-Path $runtimePath "$Name.stdout.log"
$stderrPath = Join-Path $runtimePath "$Name.stderr.log"
$scriptPath = Join-Path $PSScriptRoot "train_kaggle_sed.py"

$existing = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -like "*train_kaggle_sed.py*"
}
if ($existing) {
    Write-Warning "A CRNN training process is already running: PID $($existing.ProcessId)"
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
