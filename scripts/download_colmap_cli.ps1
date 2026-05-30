# ==============================================================================
# Download and Install COLMAP CLI for Windows
# ==============================================================================
# This script downloads the precompiled COLMAP executable which doesn't require
# Python and works reliably on Windows without pycolmap compatibility issues.
#
# Usage: .\download_colmap_cli.ps1
# ==============================================================================

$ErrorActionPreference = "Stop"

Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host "🎯 COLMAP CLI Installer for Windows" -ForegroundColor Cyan
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host ""

# Configuration
$COLMAP_VERSION = "3.9.1"
$COLMAP_URL = "https://github.com/colmap/colmap/releases/download/$COLMAP_VERSION/COLMAP-$COLMAP_VERSION-windows-cuda.zip"
$COLMAP_INSTALL_DIR = "C:\Program Files\COLMAP"
$DOWNLOAD_DIR = "$env:TEMP\colmap_download"

Write-Host "📦 Step 1: Creating download directory..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $DOWNLOAD_DIR | Out-Null

Write-Host "⬇️  Step 2: Downloading COLMAP $COLMAP_VERSION (with CUDA support)..." -ForegroundColor Yellow
$zipPath = "$DOWNLOAD_DIR\colmap.zip"

try {
    Invoke-WebRequest -Uri $COLMAP_URL -OutFile $zipPath -UseBasicParsing
    Write-Host "✅ Download complete" -ForegroundColor Green
} catch {
    Write-Host "❌ Download failed: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Alternative download:" -ForegroundColor Yellow
    Write-Host "  1. Visit: https://github.com/colmap/colmap/releases" -ForegroundColor White
    Write-Host "  2. Download: COLMAP-$COLMAP_VERSION-windows-cuda.zip" -ForegroundColor White
    Write-Host "  3. Extract to: $COLMAP_INSTALL_DIR" -ForegroundColor White
    Write-Host "  4. Add to PATH: $COLMAP_INSTALL_DIR\bin" -ForegroundColor White
    exit 1
}

Write-Host "📂 Step 3: Extracting COLMAP..." -ForegroundColor Yellow
try {
    Expand-Archive -Path $zipPath -DestinationPath $DOWNLOAD_DIR -Force
    
    # Find the extracted folder (it may have a version-specific name)
    $extractedFolder = Get-ChildItem -Path $DOWNLOAD_DIR -Directory | Select-Object -First 1
    
    # Check if we need admin rights
    if (Test-Path $COLMAP_INSTALL_DIR) {
        Remove-Item -Path $COLMAP_INSTALL_DIR -Recurse -Force -ErrorAction SilentlyContinue
    }
    
    # Try to move to Program Files (requires admin)
    try {
        Move-Item -Path $extractedFolder.FullName -Destination $COLMAP_INSTALL_DIR -Force
        Write-Host "✅ COLMAP installed to: $COLMAP_INSTALL_DIR" -ForegroundColor Green
    } catch {
        # Fallback to user directory if no admin rights
        $COLMAP_INSTALL_DIR = "$env:LOCALAPPDATA\COLMAP"
        Move-Item -Path $extractedFolder.FullName -Destination $COLMAP_INSTALL_DIR -Force
        Write-Host "✅ COLMAP installed to: $COLMAP_INSTALL_DIR (user directory)" -ForegroundColor Green
    }
    
} catch {
    Write-Host "❌ Extraction failed: $_" -ForegroundColor Red
    exit 1
}

Write-Host "🔧 Step 4: Adding COLMAP to PATH..." -ForegroundColor Yellow
$colmapBinPath = "$COLMAP_INSTALL_DIR\bin"

# Add to user PATH (doesn't require admin)
$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($currentPath -notlike "*$colmapBinPath*") {
    [Environment]::SetEnvironmentVariable(
        "Path",
        "$currentPath;$colmapBinPath",
        "User"
    )
    Write-Host "✅ Added to PATH (restart terminal to use)" -ForegroundColor Green
} else {
    Write-Host "✅ Already in PATH" -ForegroundColor Green
}

Write-Host "🧹 Step 5: Cleaning up..." -ForegroundColor Yellow
Remove-Item -Path $DOWNLOAD_DIR -Recurse -Force
Write-Host "✅ Cleanup complete" -ForegroundColor Green

Write-Host ""
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host "✅ COLMAP Installation Complete!" -ForegroundColor Green
Write-Host "===============================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "📝 Next steps:" -ForegroundColor Yellow
Write-Host "  1. RESTART your PowerShell terminal (or run: `$env:Path += `";$colmapBinPath`")" -ForegroundColor White
Write-Host "  2. Verify installation: colmap --help" -ForegroundColor White
Write-Host "  3. Check CUDA support: colmap feature_extractor --help | Select-String -Pattern 'gpu'" -ForegroundColor White
Write-Host ""
Write-Host "🚀 You can now run the COLMAP script without pycolmap!" -ForegroundColor Green
Write-Host "   The script will automatically detect and use the COLMAP CLI" -ForegroundColor White
Write-Host ""
Write-Host "===============================================================================" -ForegroundColor Cyan
