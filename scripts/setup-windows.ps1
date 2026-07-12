<#!
.SYNOPSIS
Sets up Memorycore from a cloned Git repository on Windows.

.DESCRIPTION
Creates .venv, installs the MCP service dependencies, initializes a local
SQLite database, and can optionally start the central HTTP MCP service.

.EXAMPLE
./scripts/setup-windows.ps1
./scripts/setup-windows.ps1 -StartService
#>
[CmdletBinding()]
param(
    [string]$DatabasePath = "data\memorycore.db",
    [int]$Port = 8000,
    [switch]$StartService
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.11 or newer is required. Install it from https://www.python.org/downloads/ and rerun this script."
}

$Version = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([version]$Version -lt [version]"3.11") {
    throw "Python 3.11 or newer is required; found Python $Version."
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & python -m venv .venv
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install -e ".[mcp]"

$DatabaseDirectory = Split-Path -Parent $DatabasePath
if ($DatabaseDirectory) {
    New-Item -ItemType Directory -Force -Path $DatabaseDirectory | Out-Null
}
& $Python -m memorycore.cli --db $DatabasePath init
& $Python -m memorycore.cli --db $DatabasePath doctor

Write-Host ""
Write-Host "Memorycore is ready."
Write-Host "Database: $(Join-Path $Root $DatabasePath)"
Write-Host ""
Write-Host "To start the local central MCP service later:"
Write-Host "  .\.venv\Scripts\python.exe -m memorycore.cli --db $DatabasePath serve-http --host 127.0.0.1 --port $Port"
Write-Host "MCP endpoint: http://127.0.0.1:$Port/mcp"

if ($StartService) {
    & $Python -m memorycore.cli --db $DatabasePath serve-http --host 127.0.0.1 --port $Port
}
