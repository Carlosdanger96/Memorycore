param(
    [string]$Workspace
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Push-Location $Root
try {
    $env:PYTHONPATH = if ($env:PYTHONPATH) { "$env:PYTHONPATH;$Root\src" } else { "$Root\src" }
    $Arguments = @("-m", "memorycore.demo.runner")
    if ($Workspace) { $Arguments += @("--workspace", $Workspace) }
    & python @Arguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}
