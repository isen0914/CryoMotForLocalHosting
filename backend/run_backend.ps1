param(
    [switch]$Install
)

$ErrorActionPreference = 'Stop'

function Resolve-PythonLauncher {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @{ Exe = 'python'; Args = @() }
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @{ Exe = 'py'; Args = @('-3') }
    }
    return $null
}

$backendDir = $PSScriptRoot
if (-not $backendDir) {
    $backendDir = (Get-Location).Path
}

$venvPath = Join-Path $backendDir ".venv"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"
$requirements = Join-Path $backendDir "requirements.txt"

if (-not (Test-Path $venvPath)) {
    Write-Host "Creating virtual environment (backend\\.venv)..."
    $py = Resolve-PythonLauncher
    if (-not $py) {
        throw "Python not found (neither 'python' nor Windows 'py' launcher)."
    }
    & $py.Exe @($py.Args) -m venv $venvPath
}

if ($Install) {
    if (-not (Test-Path $requirements)) {
        throw "Missing requirements.txt at: $requirements"
    }
    Write-Host "Installing requirements into venv..."
    & $pythonExe -m pip install --upgrade pip setuptools wheel
    & $pythonExe -m pip install -r $requirements
}

Write-Host "Starting backend (uvicorn)..."
Set-Location -LiteralPath $backendDir
& $pythonExe -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
