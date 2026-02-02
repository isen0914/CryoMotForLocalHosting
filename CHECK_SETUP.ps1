# Check Setup Script - Verify Installation Status
# Run this to check if everything is properly set up

Write-Host "=====================================" -ForegroundColor Cyan
Write-Host "Setup Verification Script" -ForegroundColor Cyan
Write-Host "=====================================" -ForegroundColor Cyan
Write-Host ""

$allGood = $true

# Check Python
Write-Host "[1/6] Python Installation" -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    if ($pythonVersion -match "Python 3\.([8-9]|\d{2})") {
        Write-Host "  ✓ $pythonVersion" -ForegroundColor Green
    } else {
        Write-Host "  ⚠ $pythonVersion (need 3.8+)" -ForegroundColor Yellow
        $allGood = $false
    }
} catch {
    Write-Host "  ✗ Python not found!" -ForegroundColor Red
    $allGood = $false
}

# Check pip
Write-Host "[2/6] pip Installation" -ForegroundColor Yellow
try {
    $pipVersion = pip --version 2>&1
    Write-Host "  ✓ pip installed" -ForegroundColor Green
} catch {
    Write-Host "  ✗ pip not found!" -ForegroundColor Red
    $allGood = $false
}

# Check required Python packages
Write-Host "[3/6] Python Packages" -ForegroundColor Yellow
$requiredPackages = @("fastapi", "uvicorn", "ultralytics", "numpy", "pillow", "scikit-learn", "scikit-image")
$missingPackages = @()

foreach ($package in $requiredPackages) {
    $installed = pip show $package 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ $package" -ForegroundColor Green
    } else {
        Write-Host "  ✗ $package (missing)" -ForegroundColor Red
        $missingPackages += $package
        $allGood = $false
    }
}

# Check model files
Write-Host "[4/6] Model Files" -ForegroundColor Yellow
$modelFound = $false
if (Test-Path "backend\best.quant.onnx") {
    Write-Host "  ✓ best.quant.onnx found" -ForegroundColor Green
    $modelFound = $true
}
if (Test-Path "backend\best.pt") {
    Write-Host "  ✓ best.pt found" -ForegroundColor Green
    $modelFound = $true
}
if (-not $modelFound) {
    Write-Host "  ✗ No model files found!" -ForegroundColor Red
    Write-Host "    Place best.pt or best.quant.onnx in backend/" -ForegroundColor Yellow
    $allGood = $false
}

# Check project structure
Write-Host "[5/6] Project Structure" -ForegroundColor Yellow
$requiredPaths = @(
    "backend\main.py",
    "backend\requirements.txt",
    "frontend\index.html",
    "frontend\script.js",
    "frontend\serve_frontend.py",
    "restart.ps1"
)

foreach ($path in $requiredPaths) {
    if (Test-Path $path) {
        Write-Host "  ✓ $path" -ForegroundColor Green
    } else {
        Write-Host "  ✗ $path (missing)" -ForegroundColor Red
        $allGood = $false
    }
}

# Check outputs directory
Write-Host "[6/6] Output Directory" -ForegroundColor Yellow
if (Test-Path "backend\outputs") {
    Write-Host "  ✓ backend\outputs exists" -ForegroundColor Green
} else {
    Write-Host "  ⚠ backend\outputs missing (will be created)" -ForegroundColor Yellow
}

# Summary
Write-Host ""
Write-Host "=====================================" -ForegroundColor Cyan
if ($allGood) {
    Write-Host "✓ Setup Complete - Ready to Run!" -ForegroundColor Green
    Write-Host "=====================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Run: .\restart.ps1" -ForegroundColor White
} else {
    Write-Host "✗ Setup Incomplete" -ForegroundColor Red
    Write-Host "=====================================" -ForegroundColor Cyan
    Write-Host ""
    
    if ($missingPackages.Count -gt 0) {
        Write-Host "Missing packages detected. Run to fix:" -ForegroundColor Yellow
        Write-Host "  cd backend" -ForegroundColor White
        Write-Host "  pip install -r requirements.txt" -ForegroundColor White
        Write-Host ""
    }
    
    if (-not $modelFound) {
        Write-Host "Model file missing. Actions needed:" -ForegroundColor Yellow
        Write-Host "  1. Copy best.pt or best.quant.onnx to backend/" -ForegroundColor White
        Write-Host ""
    }
    
    Write-Host "Or run the automated setup:" -ForegroundColor Yellow
    Write-Host "  .\setup.ps1" -ForegroundColor White
}

Write-Host ""
Write-Host "Press any key to exit..." -ForegroundColor Gray
pause | Out-Null
