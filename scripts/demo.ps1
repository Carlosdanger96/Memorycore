param(
    [string]$Workspace
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Push-Location $Root
try {
    if ($env:MEMORYCORE_DEMO_PYTHON) {
        $Python = $env:MEMORYCORE_DEMO_PYTHON
    } else {
        $Venv = Join-Path $Root ".demo-venv"
        $Python = Join-Path $Venv "Scripts\python.exe"
        if (-not (Test-Path $Python)) {
            $Bootstrap = if ($env:PYTHON_BOOTSTRAP) { $env:PYTHON_BOOTSTRAP } else { "python" }
            & $Bootstrap -m venv $Venv
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
        & $Python -c "import memorycore, pytest, mcp" 2>$null
        if ($LASTEXITCODE -ne 0) {
            & $Python -m pip install --upgrade pip
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            & $Python -m pip install -e ".[mcp-test]"
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        }
    }
    $Arguments = @("-m", "memorycore.demo.runner")
    if ($Workspace) { $Arguments += @("--workspace", $Workspace) }
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ($env:MEMORYCORE_DEMO_SKIP_TESTS -ne "true") {
        & $Python -m pytest -q `
            tests/test_omni_demo.py tests/test_omni_experience.py `
            tests/test_omni_scanner.py tests/test_omni_audit_provider.py `
            tests/test_omni_interfaces.py tests/test_omni_audit_projection.py
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
    Write-Output "REST: `$env:MEMORYCORE_HTTP_TOKENS_FILE='C:\private\tokens.json'; memorycore-api"
    Write-Output "MCP:  `$env:MEMORYCORE_HTTP_TOKENS_FILE='C:\private\tokens.json'; `$env:MEMORYCORE_TRANSPORT='streamable-http'; memorycore-mcp"
} finally {
    Pop-Location
}
