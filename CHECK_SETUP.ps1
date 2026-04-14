# Check Setup Script - Verify Installation Status
# Run this to check if everything is properly set up

$ErrorActionPreference = 'Stop'

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "Setup Verification Script" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

$allGood = $true

$root = $PSScriptRoot
if (-not $root) {
    $root = (Get-Location).Path
}

$backendDir = Join-Path $root 'backend'
$venvPython = Join-Path $backendDir '.venv\Scripts\python.exe'

function Resolve-PythonLauncher {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @{ Exe = 'python'; Args = @() }
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @{ Exe = 'py'; Args = @('-3') }
    }
    return $null
}

Write-Host "[1/6] Python Installation" -ForegroundColor Yellow
try {
    $py = Resolve-PythonLauncher
    if (-not $py) {
        throw "Python not found"
    }
    $pythonVersion = & $py.Exe @($py.Args) --version 2>&1
    if ($pythonVersion -match "Python 3\.([8-9]|\d{2})") {
        Write-Host "  OK: $pythonVersion" -ForegroundColor Green
    } else {
        Write-Host "  WARN: $pythonVersion (need 3.8+)" -ForegroundColor Yellow
        $allGood = $false
    }
}
catch {
    Write-Host "  ERROR: Python not found" -ForegroundColor Red
    $allGood = $false
}

Write-Host "[2/6] Virtual Environment" -ForegroundColor Yellow
if (Test-Path $venvPython) {
    Write-Host "  OK: Found venv python: $venvPython" -ForegroundColor Green
} else {
    Write-Host "  ERROR: Missing venv python: $venvPython" -ForegroundColor Red
    Write-Host "         Run: .\\setup.ps1" -ForegroundColor Yellow
    $allGood = $false
}

Write-Host "[3/6] Python Packages (import test in venv)" -ForegroundColor Yellow
$requiredImports = @(
    @{ Label = 'fastapi'; ImportName = 'fastapi' },
    @{ Label = 'uvicorn'; ImportName = 'uvicorn' },
    @{ Label = 'ultralytics'; ImportName = 'ultralytics' },
    @{ Label = 'numpy'; ImportName = 'numpy' },
    @{ Label = 'Pillow'; ImportName = 'PIL' },
    @{ Label = 'scikit-learn'; ImportName = 'sklearn' },
    @{ Label = 'scikit-image'; ImportName = 'skimage' }
)
$missingPackages = @()

if (Test-Path $venvPython) {
    foreach ($req in $requiredImports) {
        $label = $req.Label
        $name = $req.ImportName
        & $venvPython -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('$name') else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  OK: $label" -ForegroundColor Green
        } else {
            Write-Host "  MISSING: $label" -ForegroundColor Red
            $missingPackages += $label
            $allGood = $false
        }
    }
}

Write-Host "[4/6] Model Files" -ForegroundColor Yellow
$modelFound = $false
if (Test-Path (Join-Path $backendDir 'best.quant.onnx')) {
    Write-Host "  OK: best.quant.onnx found" -ForegroundColor Green
    $modelFound = $true
}
if (Test-Path (Join-Path $backendDir 'best.pt')) {
    Write-Host "  OK: best.pt found" -ForegroundColor Green
    $modelFound = $true
}
if (-not $modelFound) {
    Write-Host "  ERROR: No model files found in backend/" -ForegroundColor Red
    Write-Host "         Place best.pt or best.quant.onnx in backend/" -ForegroundColor Yellow
    $allGood = $false
}

Write-Host "[5/6] Project Structure" -ForegroundColor Yellow
$requiredPaths = @(
    'backend\main.py',
    'backend\requirements.txt',
    'frontend\index.html',
    'frontend\script.js',
    'frontend\serve_frontend.py',
    'restart.ps1'
)

foreach ($path in $requiredPaths) {
    if (Test-Path (Join-Path $root $path)) {
        Write-Host "  OK: $path" -ForegroundColor Green
    } else {
        Write-Host "  ERROR: missing $path" -ForegroundColor Red
        $allGood = $false
    }
}

Write-Host "[6/6] Output Directory" -ForegroundColor Yellow
if (Test-Path (Join-Path $backendDir 'outputs')) {
    Write-Host "  OK: backend\\outputs exists" -ForegroundColor Green
} else {
    Write-Host "  WARN: backend\\outputs missing (setup will create it)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
if ($allGood) {
    Write-Host "OK: Setup Complete - Ready to Run" -ForegroundColor Green
    Write-Host "=====================================" -ForegroundColor Cyan
    Write-Host "Run: .\\restart.ps1" -ForegroundColor White
} else {
    Write-Host "ERROR: Setup Incomplete" -ForegroundColor Red
    Write-Host "=====================================" -ForegroundColor Cyan
    if ($missingPackages.Count -gt 0) {
        Write-Host "Missing packages: $($missingPackages -join ', ')" -ForegroundColor Yellow
    }
    Write-Host "Fix: run .\\setup.ps1" -ForegroundColor Yellow
}
