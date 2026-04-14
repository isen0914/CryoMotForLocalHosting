param(
    [switch]$SkipInstall
)

$ErrorActionPreference = 'Stop'

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "YOLO Motor Detection - Setup Script" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

function Resolve-PythonLauncher {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @{ Exe = 'python'; Args = @() }
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @{ Exe = 'py'; Args = @('-3') }
    }
    return $null
}

$root = $PSScriptRoot
if (-not $root) {
    $root = (Get-Location).Path
}

$backendDir = Join-Path $root 'backend'
$requirements = Join-Path $backendDir 'requirements.txt'
$venvDir = Join-Path $backendDir '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'

Write-Host "[1/5] Checking Python installation..." -ForegroundColor Yellow
$py = Resolve-PythonLauncher
if (-not $py) {
    Write-Host "  ERROR: Python not found (neither 'python' nor 'py' launcher)." -ForegroundColor Red
    Write-Host "  Install Python 3.8+ from https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host "  During install, check 'Add Python to PATH'." -ForegroundColor Yellow
    exit 1
}

try {
    $pythonVersion = & $py.Exe @($py.Args) --version 2>&1
    Write-Host "  OK: $pythonVersion" -ForegroundColor Green
}
catch {
    Write-Host "  ERROR: Failed running Python: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

Write-Host "[2/5] Creating venv (backend\\.venv)..." -ForegroundColor Yellow
if (-not (Test-Path $backendDir)) {
    Write-Host "  ERROR: backend folder not found at: $backendDir" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $venvDir)) {
    & $py.Exe @($py.Args) -m venv $venvDir
    Write-Host "  OK: Created venv: $venvDir" -ForegroundColor Green
}
else {
    Write-Host "  OK: Venv already exists: $venvDir" -ForegroundColor Green
}

if (-not (Test-Path $venvPython)) {
    Write-Host "  ERROR: Venv python not found at: $venvPython" -ForegroundColor Red
    exit 1
}

Write-Host "[3/5] Installing backend dependencies into venv..." -ForegroundColor Yellow
if (-not (Test-Path $requirements)) {
    Write-Host "  ERROR: requirements.txt not found at: $requirements" -ForegroundColor Red
    exit 1
}

if ($SkipInstall) {
    Write-Host "  NOTE: Skipping dependency installation (-SkipInstall)." -ForegroundColor Cyan
}
else {
    & $venvPython -m pip install --upgrade pip setuptools wheel
    & $venvPython -m pip install -r $requirements
    Write-Host "  OK: Dependencies installed" -ForegroundColor Green
}

Write-Host "[4/5] Checking for model files..." -ForegroundColor Yellow
$modelFound = $false
if (Test-Path (Join-Path $backendDir 'best.quant.onnx')) {
    Write-Host "  OK: Found best.quant.onnx" -ForegroundColor Green
    $modelFound = $true
}
if (Test-Path (Join-Path $backendDir 'best.pt')) {
    Write-Host "  OK: Found best.pt" -ForegroundColor Green
    $modelFound = $true
}
if (-not $modelFound) {
    Write-Host "  WARNING: No model files found in backend/" -ForegroundColor Yellow
    Write-Host "           Place best.pt or best.quant.onnx into backend/ before running detection." -ForegroundColor Yellow
}

Write-Host "[5/5] Ensuring output directories exist..." -ForegroundColor Yellow
$outputsDir = Join-Path $backendDir 'outputs'
if (-not (Test-Path $outputsDir)) {
    New-Item -ItemType Directory -Path $outputsDir | Out-Null
    Write-Host "  OK: Created backend\\outputs directory" -ForegroundColor Green
}
else {
    Write-Host "  OK: Outputs directory already exists" -ForegroundColor Green
}

Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "Setup Complete" -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "Next: run .\\restart.ps1" -ForegroundColor Yellow
