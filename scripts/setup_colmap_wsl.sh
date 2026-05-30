#!/bin/bash
################################################################################
# COLMAP Environment Setup for WSL2 with CUDA Support
################################################################################
# This script sets up a Python environment with pycolmap and CUDA support in WSL
# 
# Prerequisites:
#   - WSL2 installed (wsl --install)
#   - NVIDIA GPU with drivers installed on Windows
#   - Windows 11 or Windows 10 21H2+
#
# Usage:
#   bash setup_colmap_wsl.sh
################################################################################

set -e  # Exit on error

echo "==================================================================="
echo "🚀 Setting up COLMAP with CUDA in WSL"
echo "==================================================================="

# Check if running in WSL
if ! grep -qi microsoft /proc/version; then
    echo "❌ ERROR: This script must be run in WSL"
    exit 1
fi

echo ""
echo "📦 Step 1: Installing system dependencies..."
sudo apt-get update
sudo apt-get install -y \
    build-essential \
    cmake \
    git \
    wget \
    libboost-all-dev \
    libeigen3-dev \
    libfreeimage-dev \
    libgoogle-glog-dev \
    libgflags-dev \
    libglew-dev \
    qtbase5-dev \
    libqt5opengl5-dev

echo ""
echo "🐍 Step 2: Installing Miniconda (if not already installed)..."
if ! command -v conda &> /dev/null; then
    wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/miniconda.sh
    bash ~/miniconda.sh -b -p $HOME/miniconda3
    rm ~/miniconda.sh
    export PATH="$HOME/miniconda3/bin:$PATH"
    eval "$($HOME/miniconda3/bin/conda shell.bash hook)"
    conda init bash
    echo "✅ Miniconda installed. Please close and reopen your terminal, then run this script again."
    exit 0
else
    echo "✅ Conda already installed"
fi

echo ""
echo "🔧 Step 3: Creating conda environment with Python 3.11..."
if conda env list | grep -q "^colmap-cuda "; then
    echo "⚠️  Environment 'colmap-cuda' already exists. Removing it..."
    conda env remove -n colmap-cuda -y
fi

conda create -n colmap-cuda python=3.11 -y

echo ""
echo "🎮 Step 4: Checking CUDA availability..."
# Check if NVIDIA drivers are available in WSL
if command -v nvidia-smi &> /dev/null; then
    echo "✅ NVIDIA GPU detected:"
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
    CUDA_AVAILABLE=true
else
    echo "⚠️  No NVIDIA GPU detected. Installing CPU-only version."
    echo "   For CUDA support, ensure you have:"
    echo "   1. Windows 11 or Windows 10 21H2+"
    echo "   2. NVIDIA GPU with latest drivers on Windows"
    echo "   3. WSL2 (not WSL1)"
    CUDA_AVAILABLE=false
fi

echo ""
echo "📚 Step 5: Installing Python packages..."
eval "$(conda shell.bash hook)"
conda activate colmap-cuda

if [ "$CUDA_AVAILABLE" = true ]; then
    echo "Installing CUDA-enabled pycolmap..."
    # Install CUDA toolkit via conda
    conda install -c conda-forge cudatoolkit=11.8 -y
    
    # Try to install pycolmap with CUDA support
    pip install pycolmap[cuda] || {
        echo "⚠️  Failed to install pycolmap[cuda], falling back to CPU version"
        pip install pycolmap
    }
else
    echo "Installing CPU-only pycolmap..."
    pip install pycolmap
fi

# Install other dependencies
pip install opencv-python scipy pillow numpy tqdm

echo ""
echo "✅ Step 6: Verifying installation..."
python -c "
import pycolmap
import numpy as np
import cv2
from scipy.spatial.transform import Rotation
from PIL import Image

print('✅ All packages imported successfully')
print(f'PyColmap version: {pycolmap.__version__}')
print(f'CUDA available: {pycolmap.has_cuda}')
if pycolmap.has_cuda:
    print('🎮 GPU acceleration enabled!')
else:
    print('💻 Running in CPU mode')
"

echo ""
echo "==================================================================="
echo "✅ Setup complete!"
echo "==================================================================="
echo ""
echo "📝 Next steps:"
echo "   1. Activate the environment:"
echo "      conda activate colmap-cuda"
echo ""
echo "   2. Navigate to your project (Windows drives are mounted at /mnt/):"
echo "      cd /mnt/e/DevProjects/rmi-360-workflow-pyt"
echo ""
echo "   3. Run the COLMAP script:"
echo "      python scripts/process_360_colmap.py \\"
echo "        --input_image_path /mnt/f/25-320\\ COLMAP/panoramas \\"
echo "        --output_path /mnt/f/25-320\\ COLMAP/colmap_output \\"
echo "        --matcher sequential \\"
echo "        --pano_render_type overlapping"
echo ""
echo "   Note: Windows paths like 'F:\\folder' become '/mnt/f/folder' in WSL"
echo "==================================================================="
