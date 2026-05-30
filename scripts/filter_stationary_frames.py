#!/usr/bin/env python3
"""
Filter Stationary/Duplicate Frames for COLMAP Processing

Filters pre-extracted frames to remove stationary/duplicate frames based on similarity or motion.
Requires frames to be extracted first (use extract_video_frames.py).

This separation allows frame numbering to be preserved for GPX timestamp synchronization.

Usage:
    python filter_stationary_frames.py --input-dir frames_raw --output-dir frames_filtered --method optical_flow --motion-threshold 2.0
"""

import argparse
import cv2
import numpy as np
from pathlib import Path
from typing import List, Tuple


def compute_frame_hash(image_path: str, hash_size: int = 16) -> np.ndarray:
    """
    Compute perceptual hash (pHash) for frame similarity detection.
    
    Args:
        image_path: Path to image file
        hash_size: Hash resolution (default 16x16)
    
    Returns:
        Flattened hash array
    """
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Could not read image: {image_path}")
    
    # Resize to hash_size
    resized = cv2.resize(img, (hash_size, hash_size), interpolation=cv2.INTER_AREA)
    
    # Compute DCT
    dct = cv2.dct(np.float32(resized))
    
    # Keep top-left 8x8 (low frequencies)
    dct_low = dct[:8, :8]
    
    # Compute median
    median = np.median(dct_low)
    
    # Create binary hash
    hash_array = (dct_low > median).astype(np.uint8)
    
    return hash_array.flatten()


def compute_frame_histogram(image_path: str, bins: int = 256) -> np.ndarray:
    """Compute color histogram for similarity comparison."""
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Could not read image: {image_path}")
    
    # Resize for speed
    small = cv2.resize(img, (320, 240))
    
    # Compute histogram for each channel
    hist_b = cv2.calcHist([small], [0], None, [bins], [0, 256])
    hist_g = cv2.calcHist([small], [1], None, [bins], [0, 256])
    hist_r = cv2.calcHist([small], [2], None, [bins], [0, 256])
    
    # Normalize
    hist_b = cv2.normalize(hist_b, hist_b).flatten()
    hist_g = cv2.normalize(hist_g, hist_g).flatten()
    hist_r = cv2.normalize(hist_r, hist_r).flatten()
    
    # Concatenate all channels
    return np.concatenate([hist_b, hist_g, hist_r])


def compute_similarity_histogram(hist1: np.ndarray, hist2: np.ndarray) -> float:
    """Compute similarity between two histograms (0-1, higher = more similar)."""
    return cv2.compareHist(hist1.reshape(-1, 1), hist2.reshape(-1, 1), cv2.HISTCMP_CORREL)


def compute_similarity_hash(hash1: np.ndarray, hash2: np.ndarray) -> float:
    """Compute similarity between two hashes (0-1, higher = more similar)."""
    # Hamming distance (number of different bits)
    hamming = np.count_nonzero(hash1 != hash2)
    max_distance = len(hash1)
    
    # Convert to similarity (1 = identical, 0 = completely different)
    similarity = 1.0 - (hamming / max_distance)
    
    return similarity


def compute_optical_flow(image1_path: str, image2_path: str) -> float:
    """
    Compute optical flow motion magnitude between two frames.
    
    Returns average motion in pixels (lower = less motion, 0 = stationary).
    This is NOT a similarity score - it's a motion measure.
    """
    # Read images as grayscale
    img1 = cv2.imread(image1_path, cv2.IMREAD_GRAYSCALE)
    img2 = cv2.imread(image2_path, cv2.IMREAD_GRAYSCALE)
    
    if img1 is None or img2 is None:
        raise ValueError(f"Could not read images: {image1_path}, {image2_path}")
    
    # Resize for speed (optical flow is expensive on full resolution)
    scale = 0.25  # Process at 25% resolution
    h, w = img1.shape
    new_h, new_w = int(h * scale), int(w * scale)
    
    img1_small = cv2.resize(img1, (new_w, new_h))
    img2_small = cv2.resize(img2, (new_w, new_h))
    
    # Compute dense optical flow using Farneback method
    flow = cv2.calcOpticalFlowFarneback(
        img1_small, img2_small,
        None,
        pyr_scale=0.5,      # Image pyramid scale
        levels=3,            # Number of pyramid levels
        winsize=15,          # Averaging window size
        iterations=3,        # Iterations at each level
        poly_n=5,            # Polynomial expansion neighborhood
        poly_sigma=1.2,      # Gaussian sigma for polynomial expansion
        flags=0
    )
    
    # Calculate magnitude of flow vectors
    magnitude = np.sqrt(flow[..., 0]**2 + flow[..., 1]**2)
    
    # Return average motion (in pixels at scaled resolution)
    avg_motion = np.mean(magnitude)
    
    # Scale back to original resolution equivalent
    avg_motion_scaled = avg_motion / scale
    
    return avg_motion_scaled


def filter_similar_frames(
    input_dir: str,
    output_dir: str,
    similarity_threshold: float = 0.95,
    method: str = "histogram",
    dry_run: bool = False,
    save_removed: bool = False,
    removed_dir: str = None,
    motion_threshold: float = 2.0
) -> Tuple[List[str], List[str]]:
    """
    Filter out frames that are too similar to previous frame.
    
    Args:
        input_dir: Directory containing extracted frames
        output_dir: Directory to save filtered frames
        similarity_threshold: Threshold for similarity (0-1, higher = more strict) 
                             Used for histogram/hash methods
        method: "histogram", "hash", or "optical_flow"
        dry_run: If True, only analyze without copying files
        save_removed: If True, save removed frames to separate directory
        removed_dir: Directory to save removed frames (default: output_dir + "_removed")
        motion_threshold: Threshold for optical flow motion (pixels). 
                         Frames with motion < threshold are removed.
                         Typical: 1-3 pixels for stationary detection
    
    Returns:
        Tuple of (kept_frames, removed_frames)
    """
    
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    if not dry_run:
        output_path.mkdir(parents=True, exist_ok=True)
        
        if save_removed:
            if removed_dir is None:
                removed_path = Path(str(output_dir) + "_removed")
            else:
                removed_path = Path(removed_dir)
            removed_path.mkdir(parents=True, exist_ok=True)
    
    # Get all frames sorted by name
    frames = sorted(input_path.glob('*.jpg'))
    
    if not frames:
        print(f"No frames found in {input_dir}")
        return [], []
    
    print(f"\nAnalyzing {len(frames)} frames...")
    print(f"Method: {method}")
    
    if method == "optical_flow":
        print(f"Motion threshold: {motion_threshold} pixels")
        print(f"(Frames with motion < {motion_threshold} pixels will be removed)")
    else:
        print(f"Similarity threshold: {similarity_threshold}")
        print(f"(Frames with similarity > {similarity_threshold} will be removed)")
    
    kept_frames = []
    removed_frames = []
    
    prev_frame_path = None
    output_counter = 1
    
    for i, frame_path in enumerate(frames):
        # Compare with previous frame
        if prev_frame_path is None:
            # Always keep first frame
            keep_frame = True
            metric_value = 0.0
        else:
            if method == "optical_flow":
                # Compute motion between frames (lower = less motion)
                metric_value = compute_optical_flow(str(prev_frame_path), str(frame_path))
                keep_frame = metric_value >= motion_threshold  # Keep if motion above threshold
            elif method == "histogram":
                # Compute similarity (higher = more similar)
                prev_feature = compute_frame_histogram(str(prev_frame_path))
                curr_feature = compute_frame_histogram(str(frame_path))
                metric_value = compute_similarity_histogram(prev_feature, curr_feature)
                keep_frame = metric_value < similarity_threshold  # Keep if different enough
            elif method == "hash":
                # Compute similarity (higher = more similar)
                prev_feature = compute_frame_hash(str(prev_frame_path))
                curr_feature = compute_frame_hash(str(frame_path))
                metric_value = compute_similarity_hash(prev_feature, curr_feature)
                keep_frame = metric_value < similarity_threshold  # Keep if different enough
            else:
                raise ValueError(f"Unknown method: {method}")
        
        if keep_frame:
            kept_frames.append(str(frame_path))
            prev_frame_path = frame_path
            
            if not dry_run:
                # Copy/rename frame to output directory
                output_name = f"frame_{output_counter:05d}.jpg"
                output_file = output_path / output_name
                
                import shutil
                shutil.copy2(frame_path, output_file)
            
            output_counter += 1
        else:
            removed_frames.append(str(frame_path))
            
            if not dry_run and save_removed:
                # Save removed frame to removed directory for debugging
                # Include metric value in filename for analysis
                if method == "optical_flow":
                    removed_name = f"removed_{i+1:05d}_motion{metric_value:.2f}.jpg"
                else:
                    removed_name = f"removed_{i+1:05d}_sim{metric_value:.3f}.jpg"
                removed_file = removed_path / removed_name
                
                import shutil
                shutil.copy2(frame_path, removed_file)
        
        # Progress indicator
        if (i + 1) % 100 == 0:
            print(f"  Processed {i+1}/{len(frames)} frames... "
                  f"(kept: {len(kept_frames)}, removed: {len(removed_frames)})")
    
    print(f"\n{'DRY RUN - ' if dry_run else ''}Results:")
    print(f"  Original frames: {len(frames)}")
    print(f"  Kept frames: {len(kept_frames)} ({len(kept_frames)/len(frames)*100:.1f}%)")
    print(f"  Removed frames: {len(removed_frames)} ({len(removed_frames)/len(frames)*100:.1f}%)")
    print(f"  Reduction: {len(removed_frames)/len(frames)*100:.1f}%")
    
    if not dry_run:
        print(f"\n✓ Filtered frames saved to: {output_dir}")
        if save_removed:
            print(f"✓ Removed frames saved to: {removed_path}")
    
    return kept_frames, removed_frames


def main():
    parser = argparse.ArgumentParser(
        description="Filter stationary/duplicate frames for COLMAP"
    )
    
    # Input parameters
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing pre-extracted frames"
    )
    
    # Common parameters
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for filtered frames"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.95,
        help="Similarity threshold (0-1, default 0.95). Higher = more aggressive filtering"
    )
    parser.add_argument(
        "--motion-threshold",
        type=float,
        default=2.0,
        help="Motion threshold in pixels for optical_flow method (default 2.0)"
    )
    parser.add_argument(
        "--method",
        choices=["histogram", "hash", "optical_flow"],
        default="histogram",
        help="Similarity detection method (default: histogram)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze only, don't copy files"
    )
    parser.add_argument(
        "--save-removed",
        action="store_true",
        help="Save removed frames to separate directory for debugging"
    )
    parser.add_argument(
        "--removed-dir",
        help="Directory to save removed frames (default: output_dir + '_removed')"
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("Stationary Frame Filter for COLMAP")
    print("=" * 70)
    print(f"\nInput: {args.input_dir}")
    print(f"Output: {args.output_dir}")
    print(f"Method: {args.method}")
    
    # Filter frames
    print(f"\nFiltering similar/stationary frames...")
    kept, removed = filter_similar_frames(
        args.input_dir,
        args.output_dir,
        args.threshold,
        args.method,
        args.dry_run,
        args.save_removed,
        args.removed_dir,
        args.motion_threshold
    )
    
    print("\n" + "=" * 70)
    print("RECOMMENDATIONS:")
    print("=" * 70)
    
    reduction = len(removed) / (len(kept) + len(removed)) * 100 if (kept or removed) else 0
    
    if reduction < 5:
        print(f"\n⚠️  Very little filtering ({reduction:.1f}%)")
        print(f"   Consider lowering --threshold (e.g., 0.90) for more aggressive filtering")
    elif reduction > 30:
        print(f"\n⚠️  High filtering rate ({reduction:.1f}%)")
        print(f"   If removing too many frames, increase --threshold (e.g., 0.97)")
    else:
        print(f"\n✓ Good filtering rate ({reduction:.1f}%)")
        print(f"   Threshold {args.threshold} appears well-calibrated")
    
    print(f"\nNext steps:")
    print(f"1. Review filtered frames in: {args.output_dir}")
    print(f"2. Run COLMAP processing:")
    print(f"   colmap feature_extractor --database_path database.db --image_path {args.output_dir}")
    print(f"3. Expected improvement: {reduction:.0f}% faster processing, better sequential matching")


if __name__ == "__main__":
    main()
