# Mosaic Processor Monitoring Files

This directory contains the monitoring system for Mosaic Processor progress tracking.

## 🔧 Core System Files (Required)

### `utils/mosaic_processor_monitor.py`
- **Core monitoring engine** that tracks frame generation
- Reads `frame_times.csv` files to determine expected frames
- Monitors output directories for generated JPEG files
- Runs automatically as background thread during processing
- **Required** - This is the heart of the monitoring system

### `utils/mosaic_progress_display.py`
- **Internal progress display** that runs in separate CLI window
- Launched automatically by `utils/mosaic_processor.py`
- Shows real-time progress bars and frame counts
- Closes automatically when processing completes
- **Required** - This provides the visual progress window

## 📱 External Tools

None required - monitoring is fully integrated and automatic.

## 🔄 How They Work Together

1. **User runs Mosaic Processor in ArcGIS Pro**
2. `utils/mosaic_processor.py` starts the monitoring engine (`utils/mosaic_processor_monitor.py`)
3. `utils/mosaic_processor.py` automatically launches progress window (`utils/mosaic_progress_display.py`)
4. Progress window shows real-time updates as MistikaVR generates frames
5. Window closes automatically when complete

## ✨ User Experience

- **Zero manual steps** - everything happens automatically
- **Separate window** - doesn't block ArcGIS Pro interface
- **Real-time feedback** - see progress as frames are generated
- **Clean completion** - window closes when done

## 📁 File Summary

| File | Purpose | Required | User Interaction |
|------|---------|----------|------------------|
| `utils/mosaic_processor_monitor.py` | Core monitoring logic | ✅ Required | None - automatic |
| `utils/mosaic_progress_display.py` | Auto progress window | ✅ Required | None - automatic |

The system is designed to be **completely automatic** - users simply run Mosaic Processor from ArcGIS Pro and get real-time progress monitoring without any manual steps or additional scripts.
