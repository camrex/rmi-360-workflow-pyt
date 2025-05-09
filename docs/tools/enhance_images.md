# 🖼 Tool: Enhance Images

## 🧰 Tool Name
**02 – Enhance Images**

---

## 🧭 Purpose

This tool performs **automated image enhancement** on Mosaic 360 imagery by applying a configurable series of visual adjustments, including:

- White balance correction
- Adaptive local contrast enhancement (CLAHE)
- Optional sharpening
- Saturation boost
- Gentle brightness recovery

Enhanced images can be saved to a new folder, use a suffix, or overwrite originals. The OID’s `ImagePath` field is optionally updated to point to the enhanced images.

---

## 🔧 Parameters (ArcGIS Toolbox)

| Parameter | Required | Description |
|----------|----------|-------------|
| `Oriented Imagery Dataset` | ✅ | OID Feature Class with populated `ImagePath` values |
| `Config File (optional)` | ⬜️ | Custom `config.yaml` with enhancement settings (uses default if not provided) |

---

## 🧩 Scripts & Responsibilities

| Script | Role |
|--------|------|
| `enhance_images_tool.py` | ArcGIS Toolbox wrapper |
| `enhance_images.py` | Main enhancement engine |
| `cv2` (OpenCV) | Image processing backend |
| `ThreadPoolExecutor` | Parallel processing for performance |

---

## ⚙️ Enhancement Pipeline

Each image is enhanced in the following order (configurable via `config.yaml`):

1. **White Balance**
2. **CLAHE** (Contrast Limited Adaptive Histogram Equalization)
3. **Saturation Boost**
4. **Sharpening**
5. **Brightness Recovery** (if image is too dark)

Statistics are computed before/after enhancement and logged for QA.

---

## 📂 Output Options

Defined in `image_enhancement.output.mode`:

| Mode | Behavior |
|------|----------|
| `overwrite` | Replace original images |
| `suffix` | Append `_enh` or custom suffix |
| `directory` (default) | Save to alternate subfolder (e.g., `/panos/enhanced`) |

The `ImagePath` in the OID will be updated if mode ≠ `overwrite`.

---

## 📊 Logs

If configured:
- Writes `logs/enhance_log.csv` with:
  - Brightness / contrast before and after
  - Clip limit used
  - White balance method
  - RGB means before/after
  - Enhanced file path

---

## ⚙️ Key Config Block

```yaml
image_enhancement:
  enabled: true
  adaptive: true
  output:
    mode: "directory"
    suffix: "_enh"
  apply_white_balance: true
  white_balance:
    method: "gray_world"
  apply_contrast_enhancement: true
  clahe:
    tile_grid_size: [8, 8]
    contrast_thresholds: [60, 80]
    clip_limit_low: 1.5
    clip_limit_high: 2.5
  apply_saturation_boost: true
  saturation_boost:
    factor: 1.1
  apply_sharpening: true
  sharpen:
    kernel:
      - [0, -0.3, 0]
      - [-0.3, 2.6, -0.3]
      - [0, -0.3, 0]
  brightness_recovery: true
  brightness:
    threshold: 110
    factor: 1.1
```

---

## 🧪 Example Usage

```python
from utils.enhance_images import enhance_images_in_oid

enhance_images_in_oid(
    oid_fc_path="C:/GIS/Projects/OID.gdb/Imagery",
    config_file="C:/Projects/config.yaml"
)
```

---

## ✅ Validation

Validator: `validate_tool_enhance_images(config)`

Checks:
- Output mode is valid (`overwrite`, `suffix`, `directory`)
- CLAHE settings are correct types and format
- Sharpen kernel is 3×3
- White balance method is valid
- `enabled`, `adaptive`, and other flags are boolean

---

## 📝 Notes

- Designed for use **after Mosaic Processor** but **before renaming or tagging**
- Can be run incrementally or on subsets
- Designed specifically for outdoor panoramic imagery
- Visual improvement is generally subtle but effective for final output
