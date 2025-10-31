# 📊 Mosaic Processor Progress Monitoring

The Mosaic Processor now includes real-time progress monitoring capabilities that track the rendering progress of MistikaVR by monitoring output files as they are generated.

## How It Works

1. **Frame Count Detection**: The monitor reads `frame_times.csv` files from each reel folder in the input directory to determine the expected number of frames per reel.

2. **Automatic Window Launch**: When Mosaic Processor starts, a separate CLI window automatically opens showing real-time progress.

3. **Output Monitoring**: The background monitor continuously watches the output directories (`<project_folder>/panos/original/reel*/panos/`) for generated JPEG files.

4. **Progress Display**: The CLI window shows live progress bars, frame counts, and completion status for each reel.

5. **Automatic Closure**: The monitor window automatically closes when processing completes or fails.

## Features

### Automatic Integration
- The monitoring starts automatically when `run_mosaic_processor` is called
- **Separate CLI window opens automatically** showing real-time progress
- Runs in a background thread without blocking ArcGIS Pro
- Window closes automatically when processing completes or fails
- **No user intervention required** - completely hands-off operation

### Progress Metrics
- **Per-reel progress**: Expected vs generated frame counts for each reel
- **Overall progress**: Total frames and completion percentage across all reels
- **Completion detection**: Automatically detects when all reels are finished
- **Real-time updates**: Status updates every 5 seconds during processing

### Status File Output
The monitor writes progress to: `<project_folder>/logs/mosaic_processor_progress.json`

Example status file content:
```json
{
  "timestamp": 1698768000.123,
  "timestamp_iso": "2025-10-31 14:30:00",
  "monitoring": true,
  "reels": {
    "reel_0001": {
      "expected_frames": 150,
      "generated_frames": 75,
      "progress_percent": 50.0,
      "completed": false
    },
    "reel_0002": {
      "expected_frames": 200,
      "generated_frames": 200,
      "progress_percent": 100.0,
      "completed": true
    }
  },
  "totals": {
    "expected_frames": 350,
    "generated_frames": 275,
    "progress_percent": 78.6,
    "reels_completed": 1,
    "reels_total": 2
  }
}
```

## Automatic Progress Window

When you run the Mosaic Processor from ArcGIS Pro:

1. **Automatic Launch**: A separate command prompt window opens automatically
2. **Real-time Progress**: Shows live progress bars and frame counts
3. **No User Action Required**: Window opens and closes without intervention
4. **Non-blocking**: ArcGIS Pro interface remains responsive

The progress window displays:
- Real-time progress bars for each reel
- Current frame counts (generated/expected)
- Overall completion percentage
- Automatic closure when processing completes

### External Access to Progress Data

The progress status is written to a JSON file that external scripts can read if needed:

```python
# Example: Read progress from external script
import json
from pathlib import Path

status_file = Path("D:/project/logs/mosaic_processor_progress.json")
if status_file.exists():
    try:
        with status_file.open("r", encoding="utf-8") as f:
            status = json.load(f)
    except (OSError, json.JSONDecodeError):
        status = None

    if status:
        progress = status.get("totals", {}).get("progress_percent")
    print(f"Current progress: {progress}%")
```

This allows integration with external monitoring systems if needed, but is not required for normal operation.

## Integration Examples

### PowerShell Monitoring Script
```powershell
# Monitor progress and display notifications
$statusFile = "D:\project\logs\mosaic_processor_progress.json"

while ($true) {
    if (Test-Path $statusFile) {
        $status = Get-Content $statusFile | ConvertFrom-Json
        $percent = $status.totals.progress_percent
        Write-Host "Progress: $percent% ($($status.totals.generated_frames)/$($status.totals.expected_frames) frames)"

        if ($status.totals.progress_percent -eq 100) {
            Write-Host "✅ Processing Complete!"
            break
        }
    }
    Start-Sleep 10
}
```

### Python Integration
```python
import json
from pathlib import Path

def get_mosaic_progress(project_folder):
    """Get current Mosaic Processor progress."""
    status_file = Path(project_folder) / "logs" / "mosaic_processor_progress.json"

    if not status_file.exists():
        return None

    with open(status_file) as f:
        return json.load(f)

# Usage
progress = get_mosaic_progress("D:/project")
if progress:
    print(f"Overall Progress: {progress['totals']['progress_percent']}%")
    print(f"Reels Complete: {progress['totals']['reels_completed']}/{progress['totals']['reels_total']}")
```

## Configuration

The monitoring system is automatically configured through the existing ConfigManager, but you can customize:

- **Check Interval**: How often to check for new files (default: 5 seconds)
- **Status File Location**: Where to write the progress JSON (default: logs/ folder)
- **Output Directory Structure**: Matches existing project structure

## Requirements

- `frame_times.csv` files must be present in each reel folder
- Output directory structure: `<output_base>/reel*/panos/`
- JPEG files with `.jpg` or `.jpeg` extensions (case insensitive)

## Logging

The monitor logs key events to the main application logger:
- Monitor startup/shutdown
- Reel discovery and expected frame counts
- Progress milestones (every 1% change)
- Completion detection
- Any errors encountered

## Error Handling

The monitor is designed to be robust:
- Continues monitoring if individual files can't be read
- Handles missing `frame_times.csv` files gracefully
- Logs warnings for problematic reels but continues with others
- Fails safe - main processing continues even if monitoring fails

## Performance Impact

- Minimal overhead: Only scans directories every 5 seconds
- Efficient file counting: Uses directory iteration, not file reading
- Background thread: Does not block main processing
- Automatic cleanup: Stops monitoring when processing completes
