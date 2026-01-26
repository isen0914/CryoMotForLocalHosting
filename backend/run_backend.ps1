param(
    [switch]$Install
)

# Resolve paths
$root = (Get-Location).Path
Set-Location -Path $root

$venvPath = Join-Path $root ".venv"
$pythonExe = Join-Path $venvPath "Scripts\python.exe"

if (-not (Test-Path $venvPath)) {
    Write-Host "Creating virtual environment..."
    python -m venv $venvPath
}

if ($Install) {
    Write-Host "Installing requirements into venv..."
    & $pythonExe -m pip install --upgrade pip
    & $pythonExe -m pip install -r requirements.txt
}

Write-Host "Starting backend (uvicorn)..."
& $pythonExe -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
