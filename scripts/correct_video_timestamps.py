#!/usr/bin/env python3
"""
Correct Video Timestamps to Match GPX Track

Adjusts video file creation time and embedded timestamps to align with GPX track.
This is a permanent fix that eliminates need for timeshift files.

Usage:
    # Calculate correction from calibration point
    python correct_video_timestamps.py --mode calculate --gpx track.gpx --video video.mp4
    
    # Apply correction to video file
    python correct_video_timestamps.py --mode correct --video video.mp4 --offset-seconds 18231890
"""

import argparse
import subprocess
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path


def get_video_creation_time(video_file: str) -> datetime:
    """Extract creation time from video metadata using ffprobe."""
    cmd = [
        'ffprobe',
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        video_file
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    
    data = json.loads(result.stdout)
    
    # Try to get creation time from metadata
    creation_time = None
    if 'format' in data and 'tags' in data['format']:
        tags = data['format']['tags']
        # Check common timestamp fields
        for key in ['creation_time', 'date', 'DATE']:
            if key in tags:
                creation_time = tags[key]
                break
    
    if creation_time:
        # Parse ISO format
        try:
            return datetime.fromisoformat(creation_time.replace('Z', '+00:00'))
        except:
            pass
    
    # Fallback to file creation time
    from pathlib import Path
    import os
    import platform
    
    file_path = Path(video_file)
    if platform.system() == 'Windows':
        # Windows: use file creation time
        ctime = file_path.stat().st_ctime
        return datetime.fromtimestamp(ctime)
    else:
        # Unix: use modification time
        mtime = file_path.stat().st_mtime
        return datetime.fromtimestamp(mtime)


def get_gpx_first_timestamp(gpx_file: str) -> datetime:
    """Get first timestamp from GPX track."""
    tree = ET.parse(gpx_file)
    ns = {'gpx': 'http://www.topografix.com/GPX/1/1'}
    
    first_time = tree.find('.//gpx:time', ns)
    if first_time is not None:
        timestamp = first_time.text.replace('Z', '+00:00')
        return datetime.fromisoformat(timestamp)
    
    raise ValueError("No timestamps found in GPX file")


def calculate_offset(video_time: datetime, gpx_time: datetime) -> float:
    """Calculate offset in seconds between video and GPX."""
    offset = (gpx_time - video_time).total_seconds()
    return offset


def correct_video_timestamps(
    input_video: str,
    output_video: str,
    offset_seconds: float,
    preserve_quality: bool = True
) -> None:
    """
    Create corrected video with adjusted timestamps.
    
    Args:
        input_video: Input video file path
        output_video: Output video file path
        offset_seconds: Time offset to apply (seconds)
        preserve_quality: If True, use -c copy (fast, no re-encode)
    """
    
    # Calculate new creation time
    original_time = get_video_creation_time(input_video)
    corrected_time = original_time + timedelta(seconds=offset_seconds)
    creation_time_str = corrected_time.strftime('%Y-%m-%dT%H:%M:%S.000000Z')
    
    print(f"\nTimestamp correction:")
    print(f"  Original: {original_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Corrected: {corrected_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Offset: {offset_seconds:.1f} seconds ({offset_seconds/86400:.1f} days)")
    
    # Build ffmpeg command
    cmd = [
        'ffmpeg',
        '-i', input_video,
        '-metadata', f'creation_time={creation_time_str}',
        '-metadata', f'date={creation_time_str}',
    ]
    
    if preserve_quality:
        # Fast copy - no re-encoding
        cmd.extend(['-c', 'copy'])
        print(f"\nMode: Fast copy (no re-encoding)")
    else:
        # Re-encode (slower but can fix other issues)
        cmd.extend(['-c:v', 'copy', '-c:a', 'copy'])
    
    cmd.append(output_video)
    
    print(f"\nRunning ffmpeg...")
    print(f"Command: {' '.join(cmd)}")
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print(f"\n✓ Success! Corrected video saved to: {output_video}")
    else:
        print(f"\n✗ Error: ffmpeg failed with code {result.returncode}")
        return
    
    # Verify correction
    new_time = get_video_creation_time(output_video)
    print(f"\nVerification:")
    print(f"  New timestamp: {new_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Expected: {corrected_time.strftime('%Y-%m-%d %H:%M:%S')}")
    if abs((new_time - corrected_time).total_seconds()) < 2:
        print(f"  ✓ Timestamps match!")
    else:
        print(f"  ⚠️ Timestamp mismatch - may need manual verification")


def main():
    parser = argparse.ArgumentParser(
        description="Correct video timestamps to align with GPX track"
    )
    parser.add_argument(
        "--mode",
        choices=["calculate", "correct"],
        required=True,
        help="Mode: 'calculate' offset or 'correct' video"
    )
    parser.add_argument(
        "--video",
        required=True,
        help="Input video file"
    )
    parser.add_argument(
        "--gpx",
        help="GPX track file (required for calculate mode)"
    )
    parser.add_argument(
        "--offset-seconds",
        type=float,
        help="Time offset in seconds (required for correct mode)"
    )
    parser.add_argument(
        "--output",
        help="Output video file (default: input_corrected.mp4)"
    )
    parser.add_argument(
        "--use-calibration",
        action="store_true",
        help="Use existing calibration (2:40 video = 16:05:56 GPX)"
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("Video Timestamp Correction Tool")
    print("=" * 70)
    
    if args.mode == "calculate":
        if not args.gpx:
            print("Error: --gpx required for calculate mode")
            return 1
        
        print(f"\nAnalyzing video: {args.video}")
        video_time = get_video_creation_time(args.video)
        print(f"  Video creation time: {video_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        print(f"\nAnalyzing GPX: {args.gpx}")
        gpx_time = get_gpx_first_timestamp(args.gpx)
        print(f"  GPX first timestamp: {gpx_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        offset = calculate_offset(video_time, gpx_time)
        
        print(f"\n" + "=" * 70)
        print(f"CALCULATED OFFSET")
        print("=" * 70)
        print(f"\nOffset: {offset:.1f} seconds")
        print(f"        {offset/3600:.2f} hours")
        print(f"        {offset/86400:.1f} days")
        print(f"\nInterpretation: GPX is {offset:.1f} seconds ahead of video")
        
        print(f"\n" + "=" * 70)
        print(f"NEXT STEP:")
        print("=" * 70)
        print(f"\nTo correct this video, run:")
        print(f'python {Path(__file__).name} --mode correct \\')
        print(f'    --video "{args.video}" \\')
        print(f'    --offset-seconds {offset:.1f}')
        
    elif args.mode == "correct":
        if args.offset_seconds is None and not args.use_calibration:
            print("Error: --offset-seconds required for correct mode")
            print("       (or use --use-calibration for known offset)")
            return 1
        
        offset = args.offset_seconds
        if args.use_calibration:
            # Use pre-calculated offset from calibration
            offset = 18231890.0
            print(f"\nUsing calibration offset: {offset:.1f} seconds")
        
        # Determine output filename
        if args.output:
            output_file = args.output
        else:
            video_path = Path(args.video)
            output_file = str(video_path.parent / f"{video_path.stem}_corrected{video_path.suffix}")
        
        # Correct the video
        correct_video_timestamps(
            args.video,
            output_file,
            offset,
            preserve_quality=True
        )
        
        print(f"\n" + "=" * 70)
        print(f"NEXT STEPS:")
        print("=" * 70)
        print(f"\n1. Verify corrected video plays correctly")
        print(f"2. Use Video Multiplexer WITHOUT timeshift file:")
        print(f"   - Input Video: {output_file}")
        print(f"   - Metadata File: your_track.gpx")
        print(f"   - Timeshift File: (leave empty)")
        print(f"3. GPS track should now align perfectly with video!")
    
    return 0


if __name__ == "__main__":
    exit(main())
