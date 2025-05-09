# 🛰️ Tool: Smooth GPS Noise

## 🧰 Tool Name
**04 – Smooth GPS Noise**

---

## 🧭 Purpose

This tool analyzes an Oriented Imagery Dataset (OID) for GPS irregularities using configurable spatial and geometric criteria. It optionally **flags** and/or **corrects** outlier points by:

- Detecting spatial and angular anomalies (e.g., zigzags, GPS jumps)
- Using a known centerline (if available) to identify route deviations
- Flagging outliers in a `QCFlag` field
- Optionally correcting flagged points via interpolation

---

## 🔧 Parameters (ArcGIS Toolbox)

| Parameter | Required | Description |
|----------|----------|-------------|
| `Oriented Imagery Dataset` | ✅ | Target OID feature class for analysis |
| `Reference Centerline` | ⬜️ | Optional M-enabled route for route deviation checks |
| `Flag Only (No Geometry Updates)` | ⬜️ | If checked, only flags outliers without adjusting geometry |
| `Config File` | ✅ | YAML configuration with GPS thresholds and paths |

---

## 🧱 Scripts & Workflow

| Script | Function |
|--------|----------|
| `smooth_gps_noise_tool.py` | ArcGIS wrapper and tool execution flow |
| `smooth_gps_noise.py` | Applies detection logic using geometric and optional route-based tests |
| `correct_gps_outliers.py` | Interpolates between clean points to fix flagged outliers |

---

## 📊 Outlier Detection Logic

Each point is evaluated for:

1. **Deviation from midpoint** – lateral distance from midpoint between neighbors
2. **Angle change** – deviation from straight line (acceptable range: `175–185°`)
3. **Step spacing** – deviation from expected GPS spacing (default: 5m ±0.75m)
4. **Route distance deviation** – optional; checks drift from reference line

Points failing ≥2 of the above checks are flagged as `"GPS_OUTLIER"` in `QCFlag`.

Outliers surrounded by other outliers are also flagged, even if they do not fail the threshold themselves.

---

## ⚙️ Config Settings (`config.yaml`)

```yaml
gps_smoothing:
  capture_spacing_meters: 5.0
  deviation_threshold_m: 0.5
  angle_bounds_deg: [175, 185]
  proximity_check_range_m: 0.75
  max_route_dist_deviation_m: 0.5
  smoothing_window: 2
  outlier_reason_threshold: 2
```

Optional debug CSV path:
```yaml
logs.gps_smooth_debug: "debuglog_outliers.csv"
```

---

## 🧪 Example Usage (Python)

```python
from utils.smooth_gps_noise import smooth_gps_noise
from utils.correct_gps_outliers import correct_gps_outliers

# Step 1: Flag suspect points
smooth_gps_noise(
    oid_fc="path/to/OID.gdb/OID",
    centerline_fc="path/to/centerline.gdb/Track",
    config_file="config.yaml"
)

# Step 2: Correct flagged points (optional)
correct_gps_outliers(
    oid_fc="path/to/OID.gdb/OID",
    config_file="config.yaml"
)
```

---

## 📤 Outputs

| Output | Description |
|--------|-------------|
| `QCFlag` (TEXT) | Added/updated for all flagged outliers (`"GPS_OUTLIER"`) |
| Geometry (XY) | Adjusted for flagged points (unless `Flag Only` is enabled) |
| `CameraOrientation` | Recomputed for corrected points |
| `logs/debuglog_outliers.csv` | Summary of flagged points and reasons |

---

## ✅ Validation

Validated in `validate_config.py` under:
- `validate_tool_smooth_gps_noise`
- `validate_tool_correct_gps_outliers`

Checks:
- Required keys in `gps_smoothing`
- Type validation (int/float/list)
- Ensures `angle_bounds_deg` is a 2-element list
- Ensures WKIDs are defined in `spatial_ref`

---

## 📝 Notes & Best Practices

- Use `Flag Only` for dry runs or QA before applying geometry updates
- Recommended before renaming/tagging/geocoding stages
- A well-aligned centerline improves detection near curves
- Debug CSV is useful for QA and validation of outlier detection
