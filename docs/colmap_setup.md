# COLMAP Environment Setup Guide

## Overview

This guide provides instructions for setting up a separate conda environment for COLMAP Structure-from-Motion processing. This environment is kept separate from the ArcGIS Pro Python environment to avoid dependency conflicts.

## Prerequisites

- Python 3.10 or higher (system Python or standalone installation)
- At least 5GB free disk space for environment and dependencies
- Windows, macOS, or Linux operating system

## Quick Setup

### Option 1: Automated Setup (Windows PowerShell)

Run the provided setup script:

```powershell
# Navigate to repository root
cd E:\DevProjects\rmi-360-workflow-pyt-102025\rmi-360-workflow-pyt

# Run setup script (creates venv at E:\envs\colmap-processing)
.\scripts\setup_colmap_environment.ps1

# Or specify custom location:
.\scripts\setup_colmap_environment.ps1 -EnvPath "D:\Python\colmap-env"
```

### Option 2: Manual Setup

```powershell
# Create new Python virtual environment
python -m venv E:\envs\colmap-processing

# Activate the environment
E:\envs\colmap-processing\Scripts\Activate.ps1

# Upgrade pip
python -m pip install --upgrade pip

# Install COLMAP and dependencies
pip install pycolmap opencv-python scipy pillow numpy tqdm

# Verify installation
python -c "import pycolmap; print(f'✅ pycolmap version: {pycolmap.__version__}')"
```

## Testing the Installation

Test that COLMAP is working correctly:

```powershell
# Activate environment
E:\envs\colmap-processing\Scripts\Activate.ps1

# Test pycolmap
python -c "import pycolmap; import cv2; import scipy; print('✅ All COLMAP dependencies installed successfully')"
```

## Environment Usage

### From ArcGIS Pro Tool

The "Export OID for COLMAP" tool automatically invokes the COLMAP environment via subprocess:

1. Open ArcGIS Pro and load your project
2. Open the RMI 360 Workflow toolbox
3. Run "19 - Export OID for COLMAP" tool
4. Check "Run COLMAP Processing"
5. Set "COLMAP Python Executable" to `E:\envs\colmap-processing\Scripts\python.exe`
6. Execute the tool

### From Command Line

Process exported panoramas manually:

```powershell
# Activate COLMAP environment
E:\envs\colmap-processing\Scripts\Activate.ps1

# Run COLMAP processing
python scripts/process_360_colmap.py ^
    --input_image_path D:\export\panoramas ^
    --output_path D:\export\colmap_output ^
    --matcher sequential ^
    --pano_render_type overlapping
```

## COLMAP Processing Options

### Matcher Types

- **sequential** (recommended for corridors): Matches images in order with loop detection
- **exhaustive**: Matches all image pairs (slow but thorough)
- **vocabtree**: Uses visual vocabulary tree for efficient matching
- **spatial**: Matches based on GPS coordinates (requires EXIF GPS data)

### Render Types

- **overlapping** (recommended): 4 yaw angles × 3 pitches (-35°, 0°, +35°) with 90° FOV
- **non-overlapping**: 4 yaw angles × 1 pitch (0°) with 90° FOV (faster, less accurate)
- **dense**: 6 yaw angles × 4 pitches for complex scenes (slower, more accurate)

## Output Structure

COLMAP processing creates the following output:

```
<output_dir>/
├── images/                    # Rendered perspective images (12-24 per panorama)
│   ├── pano_camera0/
│   ├── pano_camera1/
│   └── ...
├── masks/                     # Feature extraction masks
├── database.db                # COLMAP feature database
└── sparse/                    # 3D reconstruction
    └── 0/
        ├── cameras.bin        # Camera parameters
        ├── images.bin         # Image poses
        └── points3D.bin       # 3D point cloud
```

## Downstream Processing

### Gaussian Splatting

Use the COLMAP sparse reconstruction for Gaussian Splat training:

```powershell
# Example with Nerfstudio
ns-train splatfacto --data D:\export\colmap_output

# Example with vanilla 3D Gaussian Splatting
python train.py -s D:\export\colmap_output --eval
```

### Photogrammetry Export

Convert COLMAP output to other formats:

```python
import pycolmap

# Load reconstruction
reconstruction = pycolmap.Reconstruction("D:/export/colmap_output/sparse/0")

# Export to various formats
reconstruction.write_text("D:/export/colmap_output/sparse_text")  # Text format
reconstruction.export_PLY("D:/export/point_cloud.ply")            # Point cloud
```

## Troubleshooting

### Environment Not Found

If you get "Python executable not found" errors:

```powershell
# Check if environment exists
Test-Path E:\envs\colmap-processing\Scripts\python.exe

# If False, recreate environment
.\scripts\setup_colmap_environment.ps1 -Force
```

### pycolmap Import Error

If COLMAP fails to import:

```powershell
# Activate environment
E:\envs\colmap-processing\Scripts\Activate.ps1

# Reinstall pycolmap
pip install --force-reinstall pycolmap
```

### Out of Memory Errors

For large datasets (>500 images), reduce concurrency:

1. Edit `scripts/process_360_colmap.py`
2. Change `max_workers = min(32, (os.cpu_count() or 2) - 1)` to `max_workers = 4`
3. Reduce render quality: Use `--pano_render_type non-overlapping`

### Poor Reconstruction Quality

Try these adjustments:

1. **Use sequential matcher with higher overlap**:
   ```powershell
   python scripts/process_360_colmap.py ... --matcher sequential --sequential_overlap 20
   ```

2. **Use overlapping or dense render type**:
   ```powershell
   python scripts/process_360_colmap.py ... --pano_render_type overlapping
   ```

3. **Ensure images have GPS EXIF tags**: COLMAP uses GPS for spatial matching and scale estimation

## Performance Considerations

### Processing Time

Typical processing times per panorama:

- **Render**: 5-10 seconds/image
- **Feature extraction**: 2-5 seconds/virtual camera (12-24 per panorama)
- **Matching**: 1-30 seconds/pair (depends on matcher type)
- **SfM**: 10-60 seconds/image (depends on overlap and complexity)

### Hardware Recommendations

- **Minimum**: 8GB RAM, 4-core CPU, 50GB free disk space
- **Recommended**: 32GB RAM, 8-core CPU, 200GB free SSD, GPU (for Gaussian Splat training)
- **Optimal**: 64GB RAM, 16-core CPU, 500GB NVMe SSD, RTX 3080+ GPU

### Disk Space

Estimate disk space requirements:

- **Export**: ~30MB per panorama
- **Rendered images**: ~300MB per panorama (12 virtual cameras × 25MB each)
- **COLMAP database**: ~50MB per 100 images
- **Sparse reconstruction**: ~100MB per 1000 images

For 200 panoramas (~60GB), expect ~70GB total for full processing pipeline.

## Advanced Configuration

### Custom Camera Models

For specialized 360 cameras, modify virtual camera parameters in `scripts/process_360_colmap.py`:

```python
PANO_RENDER_OPTIONS["custom"] = PanoRenderOptions(
    num_steps_yaw=8,           # More yaw angles for denser coverage
    pitches_deg=(-60, -30, 0, 30, 60),  # More pitch angles for complex geometry
    hfov_deg=75.0,             # Narrower FOV for higher quality
    vfov_deg=75.0,
)
```

### GPS-Based Matching

For corridor datasets with accurate GPS, use spatial matcher:

```powershell
python scripts/process_360_colmap.py ... --matcher spatial
```

Ensure images have GPS EXIF tags (populated by `apply_exif_metadata` utility).

## Related Documentation

- [Export OID for COLMAP Tool Guide](../docs/tools/export_oid_for_colmap.md)
- [Gaussian Splatting Workflow](../docs/gaussian_splat_workflow.md) *(coming soon)*
- [COLMAP Official Docs](https://colmap.github.io/)
- [pycolmap Python API](https://github.com/colmap/pycolmap)

## Support

For issues specific to:
- **COLMAP setup**: See [COLMAP GitHub Issues](https://github.com/colmap/colmap/issues)
- **RMI 360 Workflow integration**: Open issue on this repository
- **Gaussian Splatting**: See respective framework documentation (Nerfstudio, 3DGS, etc.)
