param(
    [ValidateRange(1024, 65535)][int]$Port = 3000,
    [switch]$MockDevice
)
$ErrorActionPreference = 'Stop'
$taskAppRoot = Split-Path -Parent $PSScriptRoot
$taskNodeCommand = Get-Command node -CommandType Application -ErrorAction SilentlyContinue
$taskNode = if ($env:AURISCORE_NODE) { $env:AURISCORE_NODE }
    elseif ($taskNodeCommand) { $taskNodeCommand.Source }
    else { Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' }
if (-not (Test-Path -LiteralPath $taskNode)) {
    throw 'Node.js is unavailable. Install Node.js or set AURISCORE_NODE to its executable path.'
}
Push-Location -LiteralPath $taskAppRoot
try {
    if ($MockDevice) {
        Push-Location -LiteralPath (Join-Path $taskAppRoot 'mini-services\mock-device')
        try { & $taskNode --import tsx index.ts } finally { Pop-Location }
    } else {
        $taskNext = Join-Path $taskAppRoot 'node_modules\next\dist\bin\next'
        if (-not (Test-Path -LiteralPath $taskNext)) { throw 'Install WebApp dependencies before starting: npm ci.' }
        & $taskNode $taskNext dev -p $Port
    }
} finally { Pop-Location }
