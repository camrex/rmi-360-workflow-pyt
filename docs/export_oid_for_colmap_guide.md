# Export OID for COLMAP - Quick Start Guide

## Overview

The **Export OID for COLMAP** tool extracts selected 360 panorama images from an Oriented Imagery Dataset (OID) and prepares them for COLMAP Structure-from-Motion processing and Gaussian Splatting workflows.

## When to Use This Tool

Use this tool when you want to:

- **Create 3D reconstructions** from corridor 360 imagery
- **Generate Gaussian Splats** for high-quality 3D visualization
- **Train neural radiance fields** (NeRFs) from 360 panoramas
- **Export specific segments** of a corridor for detailed analysis
- **Process imagery offline** for photogrammetry workflows

## Quick Start

### Step 1: Setup COLMAP Environment (One-Time)

```powershell
# Run the automated setup script
.\scripts\setup_colmap_environment.ps1
```

This creates a Python virtual environment at `E:\envs\colmap-processing` with pycolmap and all dependencies. See [docs/colmap_setup.md](colmap_setup.md) for details.

### Step 2: Select OID Points in ArcGIS Pro

1. Open your ArcGIS Pro project
2. Add the OID feature class to your map
3. Use **Select by Attributes** or **Select by Location** to choose images
4. Or use **interactive selection** to pick specific points

**Example selections:**
- **Segment export**: `Sequence = 1 AND Frame >= 100 AND Frame <= 200`
- **Quality filter**: `QCFlag IS NULL OR QCFlag <> 'GPS_OUTLIER'`
- **Spatial area**: Use polygon selection tool to select region

### Step 3: Run Export Tool

1. Open **RMI 360 Imaging Workflow** toolbox
2. Run **19 - Export OID for COLMAP** tool
3. Fill in parameters:

| Parameter | Description | Example |
|-----------|-------------|---------|
| **Project Folder** | Root project directory | `D:\Projects\RMI25320` |
| **OID Feature Class** | Your OID layer (with selection) | `D:\Projects\RMI25320\gis_data\RMI25320_OID.gdb\OID` |
| **Export Directory** | Output location | `D:\Exports\corridor_segment_1` |
| **Run COLMAP Processing** | ☑ Auto-run COLMAP after export | Checked |
| **COLMAP Python Executable** | Path to Python with pycolmap | `E:\envs\colmap-processing\Scripts\python.exe` |
| **Matcher Type** | Feature matching strategy | `sequential` |
| **Render Type** | Virtual camera configuration | `overlapping` |
| **Config File** | Optional AWS config for S3 images | `D:\Projects\RMI25320\config.yaml` |

4. Click **Run**

### Step 4: Review Results

After processing completes, you'll have:

```
D:\Exports\corridor_segment_1\
├── panoramas/              # Original 360 images
│   ├── RMI25320_S1_F0100.jpg
│   ├── RMI25320_S1_F0101.jpg
│   └── ...
├── metadata.json           # GPS, orientation, OID mapping
├── export_log.txt          # Export operation log
└── colmap_output/          # COLMAP processing results (if enabled)
    ├── images/             # Rendered perspective views
    ├── masks/              # Feature extraction masks
    ├── database.db         # COLMAP feature database
    └── sparse/             # 3D reconstruction
        └── 0/
            ├── cameras.bin
            ├── images.bin
            └── points3D.bin
```

## Common Workflows

### Export Only (Manual COLMAP Processing)

**Use case**: Want to review images before processing

1. Uncheck "Run COLMAP Processing"
2. Review exported images in `panoramas/` folder
3. Manually run COLMAP when ready:

```powershell
E:\envs\colmap-processing\Scripts\Activate.ps1
python scripts/process_360_colmap.py --input_image_path D:\Exports\corridor_segment_1\panoramas --output_path D:\Exports\corridor_segment_1\colmap_output
```

### Export from S3-Hosted Images

**Use case**: Images stored in AWS S3

1. Ensure `config.yaml` has AWS credentials configured
2. Provide config file path in tool parameters
3. Tool automatically downloads from S3 during export

**Config requirements:**
```yaml
aws:
  region: us-east-1
  access_key: YOUR_ACCESS_KEY
  secret_key: YOUR_SECRET_KEY
  # OR use keyring:
  keyring_aws: true
  keyring_service_name: rmi_s3
```

### Large Dataset Processing

**Use case**: >500 panorama images

**Recommendations:**
1. Use `sequential` matcher (faster than exhaustive)
2. Use `non-overlapping` render type (fewer virtual cameras)
3. Split into multiple exports (100-200 images each)
4. Process on high-memory machine (32GB+ RAM recommended)

**Example split by sequence:**
```sql
-- Export 1
Sequence = 1

-- Export 2
Sequence = 2

-- Export 3
Sequence >= 3
```

### High-Quality 3D Reconstruction

**Use case**: Detailed architectural or structural analysis

**Settings:**
- Matcher: `exhaustive` or `vocabtree`
- Render Type: `dense`
- Ensure good image overlap (>70%)
- Remove motion-blurred or low-quality images before export

## COLMAP Processing Options

### Matcher Types

| Matcher | Best For | Speed | Quality |
|---------|----------|-------|---------|
| **sequential** | Ordered corridor imagery | ⚡⚡⚡ Fast | ⭐⭐⭐ Good |
| **exhaustive** | Small datasets (<200 images) | 🐌 Slow | ⭐⭐⭐⭐ Excellent |
| **vocabtree** | Large unordered datasets | ⚡⚡ Medium | ⭐⭐⭐⭐ Excellent |
| **spatial** | GPS-tagged corridor imagery | ⚡⚡ Medium | ⭐⭐⭐ Good |

### Render Types

| Type | Virtual Cameras/Pano | Overlap | Processing Time | Quality |
|------|---------------------|---------|-----------------|---------|
| **overlapping** | 12 (4×3 grid) | High | Medium | ⭐⭐⭐⭐ Best |
| **non-overlapping** | 4 (horizontal ring) | Low | Fast | ⭐⭐⭐ Good |
| **dense** | 24 (6×4 grid) | Very High | Slow | ⭐⭐⭐⭐⭐ Excellent |

## Downstream Processing

### Gaussian Splatting with Nerfstudio

```powershell
# Install Nerfstudio (separate virtual environment)
python -m venv E:\envs\nerfstudio
E:\envs\nerfstudio\Scripts\Activate.ps1
pip install nerfstudio

# Train Gaussian Splat
ns-train splatfacto --data D:\Exports\corridor_segment_1\colmap_output
```

### 3D Gaussian Splatting (Vanilla)

```powershell
# Clone 3DGS repository
git clone https://github.com/graphdeco-inria/gaussian-splatting
cd gaussian-splatting

# Train
python train.py -s D:\Exports\corridor_segment_1\colmap_output --eval
```

### Point Cloud Export

```python
import pycolmap

# Load COLMAP reconstruction
rec = pycolmap.Reconstruction("D:/Exports/corridor_segment_1/colmap_output/sparse/0")

# Export to PLY format
rec.export_PLY("D:/Exports/point_cloud.ply")
```

## Troubleshooting

### "No features found matching selection criteria"

**Cause**: No OID points selected or selection cleared

**Solution**: Re-apply selection in ArcGIS Pro before running tool

### "Insufficient disk space for export"

**Cause**: Not enough free space on target drive

**Solution**: 
- Free up disk space (estimate ~30-50MB per panorama)
- Choose different export directory on larger drive
- Use compression or external storage

### "Failed to download from S3"

**Cause**: AWS credentials missing or incorrect

**Solution**:
- Verify `config.yaml` has correct AWS credentials
- Test S3 access: `aws s3 ls s3://your-bucket/`
- Check IAM permissions for bucket access

### "COLMAP processing failed"

**Cause**: Environment not configured or insufficient system resources

**Solutions**:
1. Verify environment exists: `Test-Path E:\envs\colmap-processing\Scripts\python.exe`
2. Recreate environment: `.\scripts\setup_colmap_environment.ps1 -Force`
3. Check COLMAP logs in `export_directory/colmap_output/`
4. Reduce image count or use lighter render settings

### Poor Reconstruction Quality

**Common issues and fixes:**

| Issue | Cause | Solution |
|-------|-------|----------|
| Sparse/missing geometry | Low image overlap | Use `overlapping` or `dense` render type |
| Registration failure | Insufficient features | Check image quality, remove blurry images |
| Scale drift | No GPS constraints | Ensure EXIF GPS tags present |
| Wrong orientation | Incorrect camera rotation | Verify `CamHeading`, `CamPitch`, `CamRoll` fields |

## Performance Benchmarks

**Test Configuration**: Intel i7-12700K, 32GB RAM, NVMe SSD

| Images | Export Time | COLMAP Time (sequential) | COLMAP Time (exhaustive) |
|--------|-------------|-------------------------|-------------------------|
| 50 | ~2 min | ~5 min | ~15 min |
| 100 | ~4 min | ~12 min | ~45 min |
| 200 | ~8 min | ~30 min | ~3 hours |
| 500 | ~20 min | ~90 min | ~12 hours |

**Disk usage estimates:**
- Export: 30MB × image_count
- COLMAP processing: +300MB × image_count (rendered views)
- Sparse reconstruction: +50-100MB (regardless of count)

## Best Practices

1. **Select representative segments** - Don't export entire corridor unless needed
2. **Filter poor quality images** - Remove GPS outliers, motion blur before export
3. **Use sequential matcher** for ordered corridor datasets
4. **Verify GPS metadata** - Improves matching and provides scale/orientation
5. **Process in batches** - For large datasets, export and process in chunks
6. **Test settings first** - Try small subset (~20 images) before full export
7. **Monitor disk space** - Ensure 2-3x image size available for processing
8. **Keep originals** - Export copies, don't modify source OID

## Related Documentation

- [COLMAP Setup Guide](colmap_setup.md) - Environment configuration
- [OID Schema Reference](../docs_legacy/SCHEMA_CHANGELOG.md) - Field definitions
- [AWS Setup](../AWS_SETUP.md) - S3 configuration for cloud-hosted images
- [Gaussian Splatting Workflows](gaussian_splat_workflow.md) *(coming soon)*

## Support Resources

- **COLMAP Official Docs**: https://colmap.github.io/
- **pycolmap API**: https://github.com/colmap/pycolmap
- **Nerfstudio**: https://docs.nerf.studio/
- **3D Gaussian Splatting**: https://github.com/graphdeco-inria/gaussian-splatting
