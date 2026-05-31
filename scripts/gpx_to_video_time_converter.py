#!/usr/bin/env python3
"""
GPX to Video Time Converter and ArcGIS Pro Timeshift Calculator

Two modes:
1. Direct ffmpeg extraction: Converts GPX timestamps to video positions
2. ArcGIS Pro Video Multiplexer: Calculates timeshift value in seconds

Useful when GoPro camera clock is incorrect but GPX logger is accurate.

Usage:
    # Calculate timeshift for ArcGIS Pro Video Multiplexer
    python gpx_to_video_time_converter.py --mode arcgis
    
    # Or convert GPX timestamps for direct ffmpeg extraction
    python gpx_to_video_time_converter.py --mode ffmpeg --gpx-start "..." --gpx-end "..."
    
Or interactive mode:
    python gpx_to_video_time_converter.py
"""

import argparse
import sys
from datetime import datetime, timedelta

# ============================================================================
# CALIBRATION SETTINGS - Update these for your video
# ============================================================================

# Video file information
from datetime import timezone
VIDEO_FILE_CREATION = datetime(2025, 3, 23, 15, 38, 26, tzinfo=timezone.utc)  # March 23, 2025 3:38:26 PM UTC

# Calibration point (known matching timestamp)
VIDEO_CALIBRATION_OFFSET_SECONDS = 160  # 2:40 into video (2 minutes 40 seconds)
GPX_CALIBRATION_TIMESTAMP = "2025-10-20T16:05:56.500000000Z"

# ============================================================================

def parse_gpx_timestamp(gpx_time_str):
    """Parse GPX timestamp string to datetime object."""
    # Handle both with and without nanoseconds
    gpx_time_str = gpx_time_str.replace("Z", "+00:00")
    
    # Try with nanoseconds first
    try:
        return datetime.fromisoformat(gpx_time_str.split('.')[0] + '+00:00')
    except ValueError:
        return datetime.fromisoformat(gpx_time_str)


def calculate_offset():
    """Calculate time offset between GPX and video."""
    gpx_ref = parse_gpx_timestamp(GPX_CALIBRATION_TIMESTAMP)
    video_ref_actual = VIDEO_FILE_CREATION + timedelta(seconds=VIDEO_CALIBRATION_OFFSET_SECONDS)
    return gpx_ref - video_ref_actual


def gpx_to_video_position(gpx_timestamp_str, offset):
    """Convert GPX timestamp to video file position in seconds."""
    gpx_time = parse_gpx_timestamp(gpx_timestamp_str)
    video_actual_time = gpx_time - offset
    video_position_seconds = (video_actual_time - VIDEO_FILE_CREATION).total_seconds()
    return video_position_seconds


def format_timestamp(seconds):
    """Convert seconds to HH:MM:SS format."""
    if seconds < 0:
        return "INVALID (before video start)"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def main():
    parser = argparse.ArgumentParser(
        description="Convert GPX timestamps to video positions OR calculate ArcGIS Pro timeshift"
    )
    parser.add_argument(
        "--mode",
        choices=["arcgis", "ffmpeg"],
        default="arcgis",
        help="Mode: 'arcgis' for Video Multiplexer timeshift, 'ffmpeg' for direct extraction"
    )
    parser.add_argument(
        "--gpx-start",
        help="GPX timestamp for corridor start (ffmpeg mode only)"
    )
    parser.add_argument(
        "--gpx-end",
        help="GPX timestamp for corridor end (ffmpeg mode only)"
    )
    parser.add_argument(
        "--video-file",
        default="video.mp4",
        help="Path to video file (for ffmpeg command output)"
    )
    parser.add_argument(
        "--output-file",
        default="corridor_segment.mp4",
        help="Path to output video file"
    )
    parser.add_argument(
        "--output-csv",
        default="timeshift.csv",
        help="Output CSV file for ArcGIS Pro Timeshift File (arcgis mode)"
    )
    
    args = parser.parse_args()
    
    # Calculate offset
    offset = calculate_offset()
    
    print("=" * 70)
    print("GPX to Video Time Converter")
    print("=" * 70)
    print("\nCalibration:")
    print(f"  Video file creation: {VIDEO_FILE_CREATION.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Video calibration point: {format_timestamp(VIDEO_CALIBRATION_OFFSET_SECONDS)} ({VIDEO_CALIBRATION_OFFSET_SECONDS}s)")
    print(f"  GPX calibration point: {GPX_CALIBRATION_TIMESTAMP}")
    print(f"  Calculated offset: {offset.days} days, {offset.seconds} seconds")
    print(f"                     (GPX is {abs(offset.days)} days ahead of video)")
    
    # Test calibration
    test_position = gpx_to_video_position(GPX_CALIBRATION_TIMESTAMP, offset)
    print(f"\n  Verification: GPX {GPX_CALIBRATION_TIMESTAMP}")
    print(f"               → Video position {format_timestamp(test_position)}")
    print(f"               → Expected: {format_timestamp(VIDEO_CALIBRATION_OFFSET_SECONDS)}")
    if abs(test_position - VIDEO_CALIBRATION_OFFSET_SECONDS) < 1:
        print("               ✓ Calibration verified!")
    else:
        print("               ✗ Calibration error!")
    
    # ========================================================================
    # MODE 1: ArcGIS Pro Video Multiplexer Timeshift
    # ========================================================================
    if args.mode == "arcgis":
        # Calculate timeshift in seconds
        # Timeshift = how many seconds the metadata is AHEAD of the video
        timeshift_seconds = offset.total_seconds()
        
        print("\n" + "=" * 70)
        print("ARCGIS PRO VIDEO MULTIPLEXER - TIMESHIFT CALCULATION")
        print("=" * 70)
        print(f"\nTimeshift: {timeshift_seconds:.1f} seconds")
        print(f"           ({timeshift_seconds/3600:.2f} hours)")
        print(f"           ({offset.days} days + {offset.seconds} seconds)")
        print(f"\nInterpretation: GPX metadata is {timeshift_seconds:.1f} seconds AHEAD of video")
        
        # Create timeshift CSV file
        import csv
        with open(args.output_csv, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['ElapsedTime', 'TimeShift'])
            writer.writerow([0, timeshift_seconds])
        
        print(f"\n✓ Created timeshift file: {args.output_csv}")
        print("\n" + "=" * 70)
        print("HOW TO USE IN ARCGIS PRO:")
        print("=" * 70)
        print("\n1. Open ArcGIS Pro")
        print("2. Analysis tab → Tools → Search for 'Video Multiplexer'")
        print("3. Set parameters:")
        print(f"   - Input Video File: {args.video_file}")
        print("   - Metadata File: your_gps_track.gpx")
        print("   - Output Video File: output_geospatial_video.ts")
        print(f"   - Timeshift File: {args.output_csv}")
        print("4. Run the tool")
        print("5. Add the output .ts file to your map")
        print("6. Use Select by Location to find video segment matching panoramas")
        print("\nThe timeshift file tells Video Multiplexer to adjust GPX timestamps")
        print(f"by {timeshift_seconds:.1f} seconds to match the video timeline.")
        
        return
    
    # ========================================================================
    # MODE 2: Direct ffmpeg Extraction
    # ========================================================================
    if args.gpx_start and args.gpx_end:
        gpx_start = args.gpx_start
        gpx_end = args.gpx_end
    else:
        print("\n" + "=" * 70)
        print("Enter GPX timestamps (from ArcGIS Pro spatial query):")
        print("=" * 70)
        gpx_start = input("\nGPX Start timestamp: ").strip()
        gpx_end = input("GPX End timestamp: ").strip()
    
    # Convert timestamps
    try:
        start_seconds = gpx_to_video_position(gpx_start, offset)
        end_seconds = gpx_to_video_position(gpx_end, offset)
        
        start_time = format_timestamp(start_seconds)
        end_time = format_timestamp(end_seconds)
        duration = end_seconds - start_seconds
        
        print("\n" + "=" * 70)
        print("CONVERSION RESULTS")
        print("=" * 70)
        print(f"\nGPX Start: {gpx_start}")
        print(f"  → Video position: {start_time} ({start_seconds:.1f}s)")
        print(f"\nGPX End: {gpx_end}")
        print(f"  → Video position: {end_time} ({end_seconds:.1f}s)")
        print(f"\nDuration: {duration:.1f} seconds ({duration/60:.2f} minutes)")
        
        # Generate ffmpeg command
        print("\n" + "=" * 70)
        print("FFMPEG EXTRACTION COMMAND")
        print("=" * 70)
        print(f'\nffmpeg -i "{args.video_file}" ^')
        print(f'    -ss {start_time} ^')
        print(f'    -to {end_time} ^')
        print('    -c copy ^')
        print(f'    "{args.output_file}"')
        
        # Frame extraction command
        print("\n" + "=" * 70)
        print("FRAME EXTRACTION COMMAND (after video extraction)")
        print("=" * 70)
        print(f'\nffmpeg -i "{args.output_file}" ^')
        print('    -vf "select=\'not(mod(n,10))\'" ^')
        print('    -vsync vfr ^')
        print('    -q:v 2 ^')
        print('    "gopro_frames/frame_%04d.jpg"')
        print("\nNote: Extracting every 10th frame (adjust based on walking speed)")
        print("      At 30fps, this gives ~0.5m spacing for normal walking")
        
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
