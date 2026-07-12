[CmdletBinding()]
param(
    [string]$DatabasePath = "data\memorycore.db"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "No virtual environment found. Run .\scripts\setup-windows.ps1 first."
}

& $Python -m memorycore.cli --db $DatabasePath doctor
& $Python -m compileall src tests
& $Python -m pip install -e ".[mcp-test]"
& $Python -m pytest -q
