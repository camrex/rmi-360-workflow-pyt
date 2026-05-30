#!/usr/bin/env python3
"""
Extract Frames from Video for COLMAP Processing

Extracts frames at specified interval with optional crop and quality settings.
Preserves frame numbering for timestamp synchronization with GPX tracks.

Usage:
    python extract_video_frames.py --video input.mp4 --output-dir frames_raw --frame-interval 10 --crop '3840:2560:0:0'
"""

import argparse
import subprocess
from pathlib import Path


def check_ffmpeg() -> str:
    """Check if ffmpeg is available and return path."""
    import shutil
    
    # Try to find ffmpeg in PATH
    ffmpeg_path = shutil.which('ffmpeg')
    
    if ffmpeg_path:
        return 'ffmpeg'
    
    # Common installation locations on Windows
    common_paths = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
    ]
    
    for path in common_paths:
        if Path(path).exists():
            return path
    
    raise FileNotFoundError(
        "ffmpeg not found. Please install ffmpeg:\n"
        "  Option 1: choco install ffmpeg\n"
        "  Option 2: Download from https://ffmpeg.org/download.html\n"
        "  Option 3: Add ffmpeg to PATH"
    )


def extract_frames_ffmpeg(
    video_file: str,
    output_dir: str,
    frame_interval: int = 10,
    crop: str = None,
    quality: int = 1
) -> int:
    """Extract frames using ffmpeg."""
    if not Path(video_file).exists():
        raise FileNotFoundError(f"Video file not found: {video_file}")
    if frame_interval <= 0:
        raise ValueError(f"frame_interval must be positive, got {frame_interval}")
    
    # Check for ffmpeg
    ffmpeg_cmd = check_ffmpeg()
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Build ffmpeg command
    vf_filters = [f"select='not(mod(n,{frame_interval}))'"]
    if crop:
        vf_filters.append(f"crop={crop}")
    
    vf_string = ",".join(vf_filters)
    
    cmd = [
        ffmpeg_cmd,
        '-i', video_file,
        '-vf', vf_string,
        '-vsync', 'vfr',
        '-q:v', str(quality),
        '-pix_fmt', 'yuvj420p',
        str(output_path / 'frame_%05d.jpg')
    ]
    
    print(f"Extracting frames from {video_file}...")
    print(f"Command: {' '.join(cmd)}")
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        frame_count = len(list(output_path.glob('*.jpg')))
        print(f"✓ Extracted {frame_count} frames to {output_dir}")
        return frame_count
    else:
        print(f"✗ Error extracting frames")
        raise RuntimeError("ffmpeg extraction failed")


def main():
    parser = argparse.ArgumentParser(
        description="Extract frames from video for COLMAP processing"
    )
    
    parser.add_argument(
        "--video",
        required=True,
        help="Video file to extract frames from"
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for extracted frames"
    )
    parser.add_argument(
        "--frame-interval",
        type=int,
        default=10,
        help="Extract every Nth frame from video (default: 10)"
    )
    parser.add_argument(
        "--crop",
        help="Crop filter (e.g., '3840:2560:0:0' for w:h:x:y)"
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=1,
        help="JPEG quality for extraction (1-31, lower=better, default: 1)"
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("Video Frame Extraction")
    print("=" * 70)
    print(f"\nVideo: {args.video}")
    print(f"Output: {args.output_dir}")
    print(f"Interval: Every {args.frame_interval} frames")
    if args.crop:
        print(f"Crop: {args.crop}")
    print(f"Quality: {args.quality}")
    
    frame_count = extract_frames_ffmpeg(
        args.video,
        args.output_dir,
        args.frame_interval,
        args.crop,
        args.quality
    )
    
    print("\n" + "=" * 70)
    print("Extraction Complete")
    print("=" * 70)
    print(f"\nExtracted {frame_count} frames")
    print(f"\nNext steps:")
    print(f"1. Match frames to GPX timestamps if needed")
    print(f"2. Filter stationary frames:")
    print(f"   python scripts/filter_stationary_frames.py --input-dir {args.output_dir} --output-dir frames_filtered")


if __name__ == "__main__":
    main()
