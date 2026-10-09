param()

$ErrorActionPreference = "Stop"
$resultsRoot = $PSScriptRoot
$repoRoot = Split-Path -Parent $resultsRoot
$aiRoot = Join-Path $repoRoot "AI-Pipeline"
$webRoot = Join-Path $repoRoot "WebApp"
$mockRoot = Join-Path $webRoot "mini-services\mock-device"
$logsRoot = Join-Path $resultsRoot "logs"
$metadataRoot = Join-Path $resultsRoot "metadata"
$rawRoot = Join-Path $resultsRoot "raw"

foreach ($directory in @($logsRoot, $metadataRoot, $rawRoot)) {
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
}

$python = Join-Path $aiRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing AI-Pipeline/.venv. Create it and install requirements-cnn.txt before running this collector."
}

$records = [System.Collections.Generic.List[object]]::new()

function Invoke-Captured {
    param(
        [string]$Name,
        [string]$Executable,
        [string[]]$Arguments,
        [string]$WorkingDirectory,
        [string]$LogName,
        [bool]$Gate = $true
    )
    $started = Get-Date
    Push-Location $WorkingDirectory
    try {
        $output = & $Executable @Arguments 2>&1 | Out-String
        $exitCode = $LASTEXITCODE
        if ($null -eq $exitCode) { $exitCode = 0 }
    } catch {
        $output = ($_ | Out-String)
        $exitCode = 1
    } finally {
        Pop-Location
    }
    $finished = Get-Date
    $logPath = Join-Path $logsRoot $LogName
    [IO.File]::WriteAllText($logPath, $output, [Text.UTF8Encoding]::new($false))
    $records.Add([pscustomobject]@{
        name = $Name
        gate = $Gate
        exit_code = [int]$exitCode
        passed = ($exitCode -eq 0)
        duration_seconds = [math]::Round(($finished - $started).TotalSeconds, 3)
        started_at = $started.ToUniversalTime().ToString("o")
        finished_at = $finished.ToUniversalTime().ToString("o")
        log = "logs/$LogName"
    })
}

$runStarted = Get-Date

Invoke-Captured "AI bytecode compilation" $python @("-m", "compileall", "-q", "src", "scripts", "tests") $aiRoot "ai-compile.log"
Invoke-Captured "AI pytest suite" $python @(
    "-m", "pytest", "-q",
    "--junitxml=$resultsRoot\ai-pytest-junit.xml",
    "--basetemp=$rawRoot\pytest-temp"
) $aiRoot "ai-pytest.log"
Invoke-Captured "AI installed dependencies" $python @("-m", "pip", "freeze", "--all") $aiRoot "ai-pip-freeze.txt" $false
Invoke-Captured "WebApp ESLint" "npm.cmd" @("run", "lint") $webRoot "web-eslint.log"
Invoke-Captured "WebApp TypeScript" "npx.cmd" @("tsc", "--noEmit") $webRoot "web-typescript.log"
Invoke-Captured "Mock-device TypeScript" "npx.cmd" @("tsc", "--noEmit") $mockRoot "mock-typescript.log"
Invoke-Captured "Next.js production build" "npm.cmd" @("run", "build") $webRoot "web-build.log"
Invoke-Captured "Web production dependency audit" "npm.cmd" @("audit", "--omit=dev", "--json") $webRoot "web-npm-audit.json" $false
Invoke-Captured "Web installed dependencies" "npm.cmd" @("ls", "--depth=0", "--json") $webRoot "web-npm-ls.json" $false

$gitCommit = (& git -C $repoRoot rev-parse HEAD).Trim()
$gitBranch = (& git -C $repoRoot branch --show-current).Trim()
$gitStatus = (& git -C $repoRoot status --porcelain=v1 | Out-String)
$wavCount = (Get-ChildItem -Path (Join-Path $aiRoot "data\external") -Recurse -Filter "*.wav" -File -ErrorAction SilentlyContinue | Measure-Object).Count

$environment = [ordered]@{
    generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    timezone = (Get-TimeZone).Id
    operating_system = [Environment]::OSVersion.VersionString
    powershell = $PSVersionTable.PSVersion.ToString()
    python = (& $python --version 2>&1 | Out-String).Trim()
    node = (& node --version 2>&1 | Out-String).Trim()
    npm = (& npm.cmd --version 2>&1 | Out-String).Trim()
    git_commit = $gitCommit
    git_branch = $gitBranch
    working_tree_porcelain_at_collection = $gitStatus.TrimEnd()
    real_external_wav_count = $wavCount
}
$environment | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $metadataRoot "environment.json") -Encoding utf8NoBOM

$runFinished = Get-Date
$gates = @($records | Where-Object gate)
$summary = [ordered]@{
    schema_version = 1
    generated_at_utc = $runFinished.ToUniversalTime().ToString("o")
    git_commit = $gitCommit
    git_branch = $gitBranch
    overall_passed = (($gates | Where-Object { -not $_.passed }).Count -eq 0)
    gate_count = $gates.Count
    gate_passed = ($gates | Where-Object passed).Count
    gate_failed = ($gates | Where-Object { -not $_.passed }).Count
    informational_check_count = (@($records | Where-Object { -not $_.gate })).Count
    duration_seconds = [math]::Round(($runFinished - $runStarted).TotalSeconds, 3)
    real_external_wav_count = $wavCount
    tests = $records
}
$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $resultsRoot "summary.json") -Encoding utf8NoBOM

if (-not $summary.overall_passed) {
    exit 1
}
