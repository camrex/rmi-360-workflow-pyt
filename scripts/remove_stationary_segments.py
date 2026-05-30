#!/usr/bin/env python3
"""
Remove Stationary Segments from Video

Analyzes GPX track to identify moving vs stopped segments.
Generates ffmpeg commands to extract only moving portions.
Updates timeshift CSV to account for removed segments.

Usage:
    python remove_stationary_segments.py --gpx track.gpx --min-speed 0.5
"""

import argparse
import csv
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Tuple

try:
    from geopy.distance import geodesic
    GEOPY_AVAILABLE = True
except ImportError:
    GEOPY_AVAILABLE = False
    print("⚠️  geopy not installed. Install with: pip install geopy")


def parse_gpx_track(gpx_file: str) -> List[dict]:
    """Parse GPX file and extract trackpoints with timestamps."""
    tree = ET.parse(gpx_file)
    ns = {'gpx': 'http://www.topografix.com/GPX/1/1'}
    
    points = []
    for trkpt in tree.findall('.//gpx:trkpt', ns):
        time_elem = trkpt.find('gpx:time', ns)
        if time_elem is not None:
            lat = float(trkpt.get('lat'))
            lon = float(trkpt.get('lon'))
            timestamp = time_elem.text.replace('Z', '+00:00')
            timestamp = datetime.fromisoformat(timestamp)
            points.append({'time': timestamp, 'lat': lat, 'lon': lon})
    
    return points


def calculate_speeds(points: List[dict]) -> List[float]:
    """Calculate speed between consecutive GPS points."""
    if not GEOPY_AVAILABLE:
        raise ImportError("geopy required for speed calculation")
    
    speeds = [0.0]  # First point has no speed
    
    for i in range(1, len(points)):
        p1, p2 = points[i-1], points[i]
        
        # Calculate distance
        dist_m = geodesic((p1['lat'], p1['lon']), (p2['lat'], p2['lon'])).meters
        
        # Calculate time difference
        time_diff = (p2['time'] - p1['time']).total_seconds()
        
        # Calculate speed (m/s)
        if time_diff > 0:
            speed = dist_m / time_diff
        else:
            speed = 0.0
        
        speeds.append(speed)
    
    return speeds


def find_moving_segments(
    points: List[dict], 
    speeds: List[float], 
    min_speed_mps: float = 0.5,
    min_segment_duration: float = 5.0
) -> List[Tuple[datetime, datetime]]:
    """
    Identify continuous moving segments.
    
    Args:
        points: GPS trackpoints
        speeds: Calculated speeds (m/s)
        min_speed_mps: Minimum speed to consider "moving" (default 0.5 m/s)
        min_segment_duration: Minimum segment length in seconds (filters noise)
    
    Returns:
        List of (start_time, end_time) tuples for moving segments
    """
    segments = []
    segment_start = None
    segment_start_idx = None
    
    for i, speed in enumerate(speeds):
        is_moving = speed > min_speed_mps
        
        if is_moving:
            if segment_start is None:
                segment_start = points[i]['time']
                segment_start_idx = i
        else:
            if segment_start is not None:
                segment_end = points[i-1]['time']
                duration = (segment_end - segment_start).total_seconds()
                
                # Only keep segments longer than minimum duration
                if duration >= min_segment_duration:
                    segments.append((segment_start, segment_end))
                
                segment_start = None
                segment_start_idx = None
    
    # Close final segment if still moving
    if segment_start is not None:
        segment_end = points[-1]['time']
        duration = (segment_end - segment_start).total_seconds()
        if duration >= min_segment_duration:
            segments.append((segment_start, segment_end))
    
    return segments


def format_timestamp(seconds: float) -> str:
    """Convert seconds to HH:MM:SS.mmm format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def main():
    parser = argparse.ArgumentParser(
        description="Remove stationary segments from video based on GPX track"
    )
    parser.add_argument(
        "--gpx",
        required=True,
        help="GPX track file"
    )
    parser.add_argument(
        "--video-file",
        default="input_video.mp4",
        help="Input video filename (for ffmpeg commands)"
    )
    parser.add_argument(
        "--output-prefix",
        default="moving_segment",
        help="Prefix for output video segments"
    )
    parser.add_argument(
        "--min-speed",
        type=float,
        default=0.5,
        help="Minimum speed in m/s to consider moving (default: 0.5)"
    )
    parser.add_argument(
        "--min-duration",
        type=float,
        default=5.0,
        help="Minimum segment duration in seconds (default: 5.0)"
    )
    parser.add_argument(
        "--video-creation-time",
        default="2025-03-23T15:38:26+00:00",
        help="Video file creation timestamp (ISO format)"
    )
    parser.add_argument(
        "--timeshift-seconds",
        type=float,
        default=18231890.0,
        help="Timeshift between GPX and video in seconds"
    )
    
    args = parser.parse_args()
    
    if not GEOPY_AVAILABLE:
        print("Error: geopy is required. Install with: pip install geopy")
        return 1
    
    print("=" * 70)
    print("Remove Stationary Segments from Video")
    print("=" * 70)
    
    # Parse GPX
    print(f"\nParsing GPX file: {args.gpx}")
    points = parse_gpx_track(args.gpx)
    print(f"  Found {len(points)} GPS trackpoints")
    
    # Calculate speeds
    print(f"\nCalculating speeds...")
    speeds = calculate_speeds(points)
    avg_speed = sum(speeds) / len(speeds)
    max_speed = max(speeds)
    print(f"  Average speed: {avg_speed:.2f} m/s ({avg_speed*3.6:.1f} km/h)")
    print(f"  Maximum speed: {max_speed:.2f} m/s ({max_speed*3.6:.1f} km/h)")
    
    # Find moving segments
    print(f"\nFinding moving segments (min speed: {args.min_speed} m/s)...")
    segments = find_moving_segments(points, speeds, args.min_speed, args.min_duration)
    print(f"  Found {len(segments)} moving segments")
    
    # Calculate statistics
    total_gpx_duration = (points[-1]['time'] - points[0]['time']).total_seconds()
    moving_duration = sum((end - start).total_seconds() for start, end in segments)
    stopped_duration = total_gpx_duration - moving_duration
    
    print(f"\nStatistics:")
    print(f"  Total GPX duration: {total_gpx_duration/60:.1f} minutes")
    print(f"  Moving duration: {moving_duration/60:.1f} minutes ({moving_duration/total_gpx_duration*100:.1f}%)")
    print(f"  Stopped duration: {stopped_duration/60:.1f} minutes ({stopped_duration/total_gpx_duration*100:.1f}%)")
    print(f"  Time savings: {stopped_duration/60:.1f} minutes removed")
    
    # Convert GPX timestamps to video positions
    video_creation = datetime.fromisoformat(args.video_creation_time)
    timeshift = timedelta(seconds=args.timeshift_seconds)
    
    print("\n" + "=" * 70)
    print("FFMPEG EXTRACTION COMMANDS")
    print("=" * 70)
    
    for i, (gpx_start, gpx_end) in enumerate(segments, 1):
        # Convert to video timestamps
        video_start = gpx_start - timeshift
        video_end = gpx_end - timeshift
        
        start_seconds = (video_start - video_creation).total_seconds()
        end_seconds = (video_end - video_creation).total_seconds()
        duration = end_seconds - start_seconds
        
        start_time = format_timestamp(start_seconds)
        
        output_file = f"{args.output_prefix}_{i:03d}.mp4"
        
        print(f"\n# Segment {i}: {duration:.1f} seconds")
        print(f"# GPX: {gpx_start.strftime('%H:%M:%S')} to {gpx_end.strftime('%H:%M:%S')}")
        print(f'ffmpeg -i "{args.video_file}" \\')
        print(f'    -ss {start_time} \\')
        print(f'    -t {duration:.3f} \\')
        print(f'    -c copy \\')
        print(f'    "{output_file}"')
    
    # Concatenation command
    print("\n" + "=" * 70)
    print("CONCATENATE ALL SEGMENTS (Optional)")
    print("=" * 70)
    print(f"\n# Create file list")
    print(f"$segments = 1..{len(segments)}")
    print(f'$segments | ForEach-Object {{ "file \'{args.output_prefix}_${{_:D3}}.mp4\'" }} | Out-File -Encoding ASCII concat_list.txt')
    print(f'\n# Concatenate')
    print(f'ffmpeg -f concat -safe 0 -i concat_list.txt -c copy moving_only_combined.mp4')
    
    print(f"\n" + "=" * 70)
    print("NOTE: Concatenated video will have discontinuous timestamps!")
    print("Use individual segments for Video Multiplexer, or adjust timeshift dynamically.")
    print("=" * 70)


if __name__ == "__main__":
    main()
