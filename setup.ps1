# YOLO Flagellar Motor Detection - Setup Script
# This script automates the setup process for new deployments

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "YOLO Motor Detection - Setup Script" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python is installed
Write-Host "[1/5] Checking Python installation..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "  ✓ Found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "  ✗ Python not found!" -ForegroundColor Red
    Write-Host "  Please install Python 3.8+ from https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host "  Make sure to check 'Add Python to PATH' during installation" -ForegroundColor Yellow
    pause
    exit 1
}

# Check if pip is installed
Write-Host "[2/5] Checking pip installation..." -ForegroundColor Yellow
try {
    $pipVersion = pip --version 2>&1
    Write-Host "  ✓ Found: $pipVersion" -ForegroundColor Green
} catch {
    Write-Host "  ✗ pip not found!" -ForegroundColor Red
    Write-Host "  Installing pip..." -ForegroundColor Yellow
    python -m ensurepip --upgrade
}

# Install backend dependencies
Write-Host "[3/5] Installing backend dependencies..." -ForegroundColor Yellow
if (Test-Path "backend\requirements.txt") {
    Push-Location backend
    Write-Host "  Installing from requirements.txt..." -ForegroundColor Cyan
    pip install -r requirements.txt
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ Backend dependencies installed successfully" -ForegroundColor Green
    } else {
        Write-Host "  ✗ Failed to install backend dependencies" -ForegroundColor Red
        Pop-Location
        pause
        exit 1
    }
    Pop-Location
} else {
    Write-Host "  ✗ backend\requirements.txt not found!" -ForegroundColor Red
    pause
    exit 1
}

# Check for model files
Write-Host "[4/5] Checking for model files..." -ForegroundColor Yellow
$modelFound = $false
if (Test-Path "backend\best.quant.onnx") {
    Write-Host "  ✓ Found: best.quant.onnx (Quantized ONNX model)" -ForegroundColor Green
    $modelFound = $true
}
if (Test-Path "backend\best.pt") {
    Write-Host "  ✓ Found: best.pt (PyTorch model)" -ForegroundColor Green
    $modelFound = $true
}
if (-not $modelFound) {
    Write-Host "  ⚠ No model files found in backend/" -ForegroundColor Yellow
    Write-Host "  Please place your trained model (best.pt or best.quant.onnx) in the backend/ directory" -ForegroundColor Yellow
}

# Create outputs directory if it doesn't exist
Write-Host "[5/5] Setting up output directories..." -ForegroundColor Yellow
if (-not (Test-Path "backend\outputs")) {
    New-Item -ItemType Directory -Path "backend\outputs" | Out-Null
    Write-Host "  ✓ Created backend\outputs directory" -ForegroundColor Green
} else {
    Write-Host "  ✓ Outputs directory already exists" -ForegroundColor Green
}

# Final summary
Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Ensure your model file (best.pt or best.quant.onnx) is in backend/" -ForegroundColor White
Write-Host "  2. Run: .\restart.ps1" -ForegroundColor White
Write-Host "  3. Access frontend at: http://localhost:8001" -ForegroundColor White
Write-Host "  4. Access backend API at: http://localhost:8000" -ForegroundColor White
Write-Host "  5. View API docs at: http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "Press any key to exit..." -ForegroundColor Gray
pause | Out-Null
