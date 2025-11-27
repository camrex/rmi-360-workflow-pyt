# ========================================================
# COLMAP Environment Setup Script
# ========================================================
# Creates a separate Python virtual environment for COLMAP processing
# to avoid conflicts with ArcGIS Pro Python environment
# ========================================================

param(
    [string]$EnvPath = "E:\envs\colmap-processing",
    [switch]$Force
)

Write-Host "`n============================================" -ForegroundColor Cyan
Write-Host "COLMAP Environment Setup" -ForegroundColor Cyan
Write-Host "============================================`n" -ForegroundColor Cyan

# Check if Python is available
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "✗ ERROR: python not found in PATH" -ForegroundColor Red
    Write-Host "  Please ensure Python 3.10+ is installed and available in your PATH" -ForegroundColor Yellow
    exit 1
}

# Check if environment already exists
$envExists = Test-Path $EnvPath

if ($envExists -and -not $Force) {
    Write-Host "✓ Environment already exists at: $EnvPath" -ForegroundColor Green
    Write-Host "`nTo recreate the environment, run with -Force flag:" -ForegroundColor Yellow
    Write-Host "  .\scripts\setup_colmap_environment.ps1 -Force" -ForegroundColor Yellow
    Write-Host "`nTo activate the environment:" -ForegroundColor Cyan
    Write-Host "  $EnvPath\Scripts\Activate.ps1" -ForegroundColor White
    exit 0
}

if ($Force -and $envExists) {
    Write-Host "Removing existing environment at $EnvPath..." -ForegroundColor Yellow
    Remove-Item -Path $EnvPath -Recurse -Force
}

# Create virtual environment
Write-Host "`nStep 1: Creating Python virtual environment..." -ForegroundColor Cyan
Write-Host "  Location: $EnvPath" -ForegroundColor White
Write-Host "  This may take a minute..." -ForegroundColor Yellow
Write-Host ""

$createResult = python -m venv $EnvPath 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ ERROR: Failed to create virtual environment" -ForegroundColor Red
    Write-Host $createResult
    exit 1
}

Write-Host "✓ Virtual environment created successfully" -ForegroundColor Green

# Upgrade pip first
Write-Host "`nStep 2: Upgrading pip..." -ForegroundColor Cyan
$pipUpgrade = & "$EnvPath\Scripts\python.exe" -m pip install --upgrade pip 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠ Warning: Failed to upgrade pip, continuing anyway..." -ForegroundColor Yellow
}

# Install COLMAP and dependencies
Write-Host "`nStep 3: Installing COLMAP and dependencies..." -ForegroundColor Cyan
Write-Host "  This may take several minutes..." -ForegroundColor Yellow
Write-Host ""

$packages = @(
    "pycolmap",
    "opencv-python",
    "scipy",
    "pillow",
    "numpy",
    "tqdm"
)

Write-Host "Installing packages: $($packages -join ', ')" -ForegroundColor White

$installResult = & "$EnvPath\Scripts\python.exe" -m pip install $packages 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ ERROR: Failed to install packages" -ForegroundColor Red
    Write-Host $installResult
    Write-Host "`nTry manually installing with:" -ForegroundColor Yellow
    Write-Host "  $EnvPath\Scripts\Activate.ps1" -ForegroundColor White
    Write-Host "  pip install pycolmap opencv-python scipy pillow numpy tqdm" -ForegroundColor White
    exit 1
}

Write-Host "✓ Packages installed successfully" -ForegroundColor Green

# Verify installation
Write-Host "`nStep 4: Verifying installation..." -ForegroundColor Cyan

$verifyScript = @"
import sys
try:
    import pycolmap
    import cv2
    import scipy
    import PIL
    import numpy
    import tqdm
    print(f'pycolmap: {pycolmap.__version__}')
    print(f'opencv: {cv2.__version__}')
    print(f'scipy: {scipy.__version__}')
    print(f'pillow: {PIL.__version__}')
    print(f'numpy: {numpy.__version__}')
    print(f'tqdm: {tqdm.__version__}')
    sys.exit(0)
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
"@

$verifyResult = & "$EnvPath\Scripts\python.exe" -c $verifyScript 2>&1

if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ ERROR: Package verification failed" -ForegroundColor Red
    Write-Host $verifyResult
    exit 1
}

Write-Host "✓ All packages verified:" -ForegroundColor Green
$verifyResult | ForEach-Object { Write-Host "  $_" -ForegroundColor White }

# Success summary
Write-Host "`n============================================" -ForegroundColor Green
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "============================================`n" -ForegroundColor Green

Write-Host "Environment Location: $EnvPath" -ForegroundColor Cyan
Write-Host "Python Executable: $EnvPath\Scripts\python.exe" -ForegroundColor Cyan

Write-Host "`nTo use this environment:" -ForegroundColor Yellow
Write-Host "  1. Activate: $EnvPath\Scripts\Activate.ps1" -ForegroundColor White
Write-Host "  2. Test:     python -c 'import pycolmap; print(pycolmap.__version__)'" -ForegroundColor White
Write-Host "  3. Process:  python scripts/process_360_colmap.py --help" -ForegroundColor White

Write-Host "`nTo use with ArcGIS Pro tool:" -ForegroundColor Yellow
Write-Host "  1. Open 'Export OID for COLMAP' tool" -ForegroundColor White
Write-Host "  2. Check 'Run COLMAP Processing'" -ForegroundColor White
Write-Host "  3. Set 'COLMAP Python Path' to: $EnvPath\Scripts\python.exe" -ForegroundColor White

Write-Host "`nFor more information, see docs/colmap_setup.md`n" -ForegroundColor Cyan
