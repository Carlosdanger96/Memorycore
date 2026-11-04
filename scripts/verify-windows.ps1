[CmdletBinding()]
param(
    [string]$DatabasePath = "data\memorycore.db"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $Uv) {
    foreach ($Candidate in @(
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        (Join-Path $env:LOCALAPPDATA "hermes\bin\uv.exe"),
        (Join-Path $env:APPDATA "uv\bin\uv.exe")
    )) {
        if (Test-Path -LiteralPath $Candidate) { $Uv = $Candidate; break }
    }
}

if (-not (Test-Path $Python)) {
    throw "No virtual environment found. Run .\scripts\setup-windows.ps1 first."
}

& $Python -m memorycore.cli --db $DatabasePath doctor
if ($LASTEXITCODE -ne 0) { throw "Memorycore doctor failed." }
& $Python -m compileall src tests
if ($LASTEXITCODE -ne 0) { throw "Python compilation failed." }
if ($Uv) {
    & $Uv pip install --python $Python -e ".[dev]"
} else {
    & $Python -m pip install -e ".[dev]"
}
if ($LASTEXITCODE -ne 0) { throw "Test dependency installation failed." }
& $Python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Memorycore tests failed." }
