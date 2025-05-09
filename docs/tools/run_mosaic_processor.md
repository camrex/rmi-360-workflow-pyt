# 🛠️ Tool: Run Mosaic Processor

## 🧰 Tool Name
**01 – Run Mosaic Processor**

## 🧭 Purpose
This tool initiates the **first step** in the Mosaic 360 imagery pipeline. It runs the Mosaic Processor CLI with the Mistika VR backend to:
- Render stitched JPEG panoramas from raw `.mp4` reels
- Automatically fix reel issues
- Integrate GPS data from `.gpx` files into the resulting images
- Normalize filenames by zero-padding frame numbers to six digits

This step is **required before image enhancement, renaming, metadata tagging, or GIS ingestion**.

---

## 🧪 Under-the-Hood Workflow

1. **Render Phase** (skips GPX):
   - Runs Mosaic Processor CLI with rendering + reel fix
   - Output is saved under:  
     `project_folder / panos / original`

2. **Pad Frame Numbers**:
   - Renames image files to ensure frame numbers use six digits (e.g., `_FR000023.jpg`)

3. **GPX Integration Phase** (skips rendering):
   - Second Mosaic Processor CLI run with GPX embedding only

4. **Logging**:
   - Console output and errors are saved to a log file in the `logs/` directory

---

## 🔌 Parameters (ArcGIS Toolbox)

| Name                        | Required | Type     | Description |
|----------------------------|----------|----------|-------------|
| `Project Folder`           | ✅       | Folder   | Root for project outputs and logs |
| `Input Reels Folder`       | ✅       | Folder   | Raw Mosaic `.mp4` reels with optional `.gpx` |
| `Config File`              | ⬜️       | File     | YAML config file (optional if using default) |
| `Mosaic GRP Template Path` | ⬜️       | File     | Overrides `executables.mosaic_processor.grp_path` |
| `Start Frame`              | ⬜️       | Integer  | First frame to process |
| `End Frame`                | ⬜️       | Integer  | Last frame to process |

---

## 🧩 Dependencies

| Script | Responsibility |
|--------|----------------|
| `mosaic_processor.py` | Core logic for CLI execution and output folder structure |
| `pad_mosaic_frame_numbers.py` | Normalizes filenames by padding frame numbers |
| `validate_config.py` | Verifies executable paths and GRP file in `executables.mosaic_processor` |

---

## 📁 Output

- **Location**:  
  `project_folder / panos / original`
- **Format**:  
  JPEG images named like `..._FR000001.jpg`
- **Log File**:  
  `logs/mosaic_processor_output.log`
- **Optional JSON Metadata**:  
  `reel_info.json` if reel number is detected

---

## 🔧 Config Sections Used

| Path | Purpose |
|------|---------|
| `executables.mosaic_processor.exe_path` | Path to Mosaic Processor CLI |
| `executables.mosaic_processor.grp_path` | Default GRP file path |
| `image_output.folders.parent` and `.original` | Defines output folder hierarchy |
| `logs.mosaic_processor_log` | Log filename |

---

## 🛑 Validation Coverage

Tool-specific validator: `validate_tool_mosaic_processor(config)`

Checks:
- `exe_path`, `grp_path`, `cfg_path` are valid and not empty
- Files exist or are resolvable (unless `"DISABLED"`)
- Types are validated (`str`)
- Errors are logged using `log_message`

---

## 📝 Notes and Best Practices

- You can run this tool **multiple times per project**, once for each reel
- Use consistent naming for input reel folders: `reel_0001`, `reel_0002`, etc.
- The output is a dependency for the following tools:
  - `Enhance Images`
  - `Rename and Tag`
  - `Add Images to OID`

---

## 🧪 Example Usage in Python

```python
from utils.mosaic_processor import run_mosaic_processor

run_mosaic_processor(
    project_folder="D:/Projects/RMI25100",
    input_dir="D:/Projects/RMI25100/raw/reel_0001",
    grp_path="D:/Calibrations/Mosaic51.grp",
    config_file="D:/Projects/RMI25100/config.yaml"
)
```
