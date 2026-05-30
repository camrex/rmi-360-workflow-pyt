"""
=============================================================================
🎯 COLMAP 360 Panorama Processing Script (scripts/process_360_colmap.py)
-----------------------------------------------------------------------------
Purpose:             Process 360 panorama images using COLMAP for Structure-from-Motion
Project:             RMI 360 Imaging Workflow Python Toolbox
Version:             1.1.0
Author:              RMI Valuation, LLC / COLMAP Community
Created:             2025-11-27
Last Updated:        2025-11-27

Description:
  Processes 360 spherical panorama images using COLMAP's incremental SfM pipeline.
  Converts panoramas to virtual perspective cameras, performs feature extraction and
  matching with rig constraints, and generates 3D reconstruction for Gaussian Splatting.
  
  Supports both pycolmap (Python API) and COLMAP CLI (standalone executable).

File Location:        /scripts/process_360_colmap.py
Called By:            tools/export_oid_for_colmap_tool.py (via subprocess)
Ext. Dependencies:    pycolmap OR colmap CLI, opencv-python, scipy, pillow, numpy, tqdm

Input Structure:
  <input_dir>/
      ├── panoramas/          # 360 source images
      └── metadata.json       # Optional: GPS/orientation metadata

Output Structure:
  <output_dir>/
      ├── images/             # Rendered perspective images
      ├── masks/              # Feature extraction masks
      ├── database.db         # COLMAP database
      ├── sparse/             # 3D reconstruction
      └── processing_log.txt  # Processing log

Usage:
  # Basic processing
  python process_360_colmap.py --input_image_path D:\\export\\panoramas --output_path D:\\colmap_output

  # With custom matcher and render options
  python process_360_colmap.py --input D:\\export\\panoramas --output D:\\colmap_output \\
      --matcher sequential --pano_render_type overlapping

Notes:
  - Requires separate conda environment with pycolmap
  - Creates virtual camera rig from 360 panoramas
  - Uses rig verification for geometric matching
  - Optimized for corridor/linear datasets
=============================================================================
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import cv2
import numpy as np
import PIL.ExifTags
import PIL.Image
from scipy.spatial.transform import Rotation
from tqdm import tqdm

# Try to import pycolmap, but allow CLI fallback
USE_PYCOLMAP_API = False
USE_COLMAP_CLI = False

try:
    import pycolmap
    from pycolmap import logging
    USE_PYCOLMAP_API = True
    
    # Check for CUDA availability
    if pycolmap.has_cuda:
        print("🎮 CUDA GPU acceleration is ENABLED (pycolmap)", file=sys.stderr)
        print(f"   This will significantly speed up feature extraction and matching!", file=sys.stderr)
    else:
        print("💻 Running in CPU-only mode (pycolmap)", file=sys.stderr)
    print("", file=sys.stderr)
    
except ImportError:
    print("⚠️  pycolmap not found, checking for COLMAP CLI...", file=sys.stderr)
    
    # Check if COLMAP CLI is available
    colmap_exe = shutil.which("colmap")
    if colmap_exe:
        USE_COLMAP_CLI = True
        print(f"✅ Found COLMAP CLI at: {colmap_exe}", file=sys.stderr)
        print("   Using COLMAP CLI for feature extraction and reconstruction", file=sys.stderr)
        print("", file=sys.stderr)
        
        # Create minimal logging for CLI mode
        class SimpleLogger:
            @staticmethod
            def info(msg):
                print(f"INFO: {msg}")
            @staticmethod
            def error(msg):
                print(f"ERROR: {msg}", file=sys.stderr)
            @staticmethod
            def warning(msg):
                print(f"WARNING: {msg}", file=sys.stderr)
            @staticmethod
            def fatal(msg):
                print(f"FATAL: {msg}", file=sys.stderr)
                sys.exit(1)
        
        logging = SimpleLogger()
    else:
        print("ERROR: Neither pycolmap nor COLMAP CLI found.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Option 1 - Install pycolmap:", file=sys.stderr)
        print("  Windows: .\\scripts\\setup_colmap_environment.ps1", file=sys.stderr)
        print("  WSL/Linux: bash scripts/setup_colmap_wsl.sh", file=sys.stderr)
        print("", file=sys.stderr)
        print("Option 2 - Install COLMAP CLI:", file=sys.stderr)
        print("  Download from: https://colmap.github.io/install.html", file=sys.stderr)
        print("  Or conda: conda install -c conda-forge colmap", file=sys.stderr)
        print("", file=sys.stderr)
        sys.exit(1)


@dataclass
class PanoRenderOptions:
    """Configuration for rendering virtual perspective cameras from panoramas."""
    num_steps_yaw: int
    pitches_deg: Sequence[float]
    hfov_deg: float
    vfov_deg: float


PANO_RENDER_OPTIONS: dict[str, PanoRenderOptions] = {
    "overlapping": PanoRenderOptions(
        num_steps_yaw=4,
        pitches_deg=(-35.0, 0.0, 35.0),
        hfov_deg=90.0,
        vfov_deg=90.0,
    ),
    # Cubemap without top and bottom images (more efficient for ground-level corridors)
    "non-overlapping": PanoRenderOptions(
        num_steps_yaw=4,
        pitches_deg=(0.0,),
        hfov_deg=90.0,
        vfov_deg=90.0,
    ),
    # Denser sampling for complex scenes
    "dense": PanoRenderOptions(
        num_steps_yaw=6,
        pitches_deg=(-45.0, -15.0, 15.0, 45.0),
        hfov_deg=75.0,
        vfov_deg=75.0,
    ),
}


def create_virtual_camera(
    pano_width: int,
    pano_height: int,
    hfov_deg: float,
    vfov_deg: float,
) -> pycolmap.Camera:
    """Create a virtual perspective camera from panorama dimensions."""
    image_width = int(pano_width * hfov_deg / 360)
    image_height = int(pano_height * vfov_deg / 180)
    focal = image_width / (2 * np.tan(np.deg2rad(hfov_deg) / 2))
    return pycolmap.Camera.create(
        0, "SIMPLE_PINHOLE", focal, image_width, image_height
    )


def get_virtual_camera_rays(camera: pycolmap.Camera) -> np.ndarray:
    """Compute ray directions for all pixels in virtual camera."""
    size = (camera.width, camera.height)
    x, y = np.indices(size).astype(np.float32)
    xy = np.column_stack([x.ravel(), y.ravel()])
    # The center of the upper left most pixel has coordinate (0.5, 0.5)
    xy += 0.5
    xy_norm = camera.cam_from_img(xy)
    rays = np.concatenate([xy_norm, np.ones_like(xy_norm[:, :1])], -1)
    rays /= np.linalg.norm(rays, axis=-1, keepdims=True)
    # Ensure float32 to reduce memory usage
    return rays.astype(np.float32)


def spherical_img_from_cam(image_size, rays_in_cam: np.ndarray) -> np.ndarray:
    """Project rays into a 360 panorama (spherical) image."""
    if image_size[0] != image_size[1] * 2:
        raise ValueError("Only 360° panoramas are supported.")
    if rays_in_cam.ndim != 2 or rays_in_cam.shape[1] != 3:
        raise ValueError(f"{rays_in_cam.shape=} but expected (N,3).")
    r = rays_in_cam.T
    yaw = np.arctan2(r[0], r[2])
    pitch = -np.arctan2(r[1], np.linalg.norm(r[[0, 2]], axis=0))
    u = (1 + yaw / np.pi) / 2
    v = (1 - pitch * 2 / np.pi) / 2
    return np.stack([u, v], -1) * image_size


def get_virtual_rotations(
    num_steps_yaw: int, pitches_deg: Sequence[float]
) -> Sequence[np.ndarray]:
    """Get the relative rotations of the virtual cameras w.r.t. the panorama."""
    # Assuming that the panos are approximately upright.
    cams_from_pano_r = []
    yaws = np.linspace(0, 360, num_steps_yaw, endpoint=False)
    for pitch_deg in pitches_deg:
        yaw_offset = (360 / num_steps_yaw / 2) if pitch_deg > 0 else 0
        for yaw_deg in yaws + yaw_offset:
            cam_from_pano_r = Rotation.from_euler(
                "XY", [-pitch_deg, -yaw_deg], degrees=True
            ).as_matrix()
            cams_from_pano_r.append(cam_from_pano_r)
    return cams_from_pano_r


def create_pano_rig_config(
    cams_from_pano_rotation: Sequence[np.ndarray], ref_idx: int = 0
) -> pycolmap.RigConfig:
    """Create a RigConfig for the given virtual rotations."""
    rig_cameras = []
    for idx, cam_from_pano_rotation in enumerate(cams_from_pano_rotation):
        if idx == ref_idx:
            cam_from_rig = None
        else:
            cam_from_ref_rotation = (
                cam_from_pano_rotation @ cams_from_pano_rotation[ref_idx].T
            )
            cam_from_rig = pycolmap.Rigid3d(
                pycolmap.Rotation3d(cam_from_ref_rotation), np.zeros(3)
            )
        rig_cameras.append(
            pycolmap.RigConfigCamera(
                ref_sensor=idx == ref_idx,
                image_prefix=f"pano_camera{idx}/",
                cam_from_rig=cam_from_rig,
            )
        )
    return pycolmap.RigConfig(cameras=rig_cameras)


class PanoProcessor:
    """Process panorama images into virtual perspective views for COLMAP."""
    
    def __init__(
        self,
        pano_image_dir: Path,
        output_image_dir: Path,
        mask_dir: Path,
        render_options: PanoRenderOptions,
    ):
        self.render_options = render_options
        self.pano_image_dir = pano_image_dir
        self.output_image_dir = output_image_dir
        self.mask_dir = mask_dir

        self.cams_from_pano_rotation = get_virtual_rotations(
            num_steps_yaw=render_options.num_steps_yaw,
            pitches_deg=render_options.pitches_deg,
        )
        self.rig_config = create_pano_rig_config(self.cams_from_pano_rotation)

        # We assign each pano pixel to the virtual camera
        # with the closest camera center.
        self.cam_centers_in_pano = np.einsum(
            "nij,i->nj", self.cams_from_pano_rotation, [0, 0, 1]
        )

        self._lock = Lock()

        # These are initialized on the first pano image
        # to avoid recomputing the rays for each pano image.
        self._camera = None
        self._pano_size = None
        self._rays_in_cam = None

    def process(self, pano_name: str):
        """Process a single panorama image into virtual perspective views."""
        pano_path = self.pano_image_dir / pano_name
        
        try:
            print(f"[DEBUG] Processing panorama: {pano_path}")
            
            try:
                pano_image = PIL.Image.open(pano_path)
                print(f"[DEBUG] Opened image: {pano_path}")
            except PIL.Image.UnidentifiedImageError:
                print(f"[DEBUG] Skipping file {pano_path} as it cannot be read.")
                logging.info(f"Skipping file {pano_path} as it cannot be read.")
                return

            pano_exif = pano_image.getexif()
            pano_image = np.asarray(pano_image)
            print(f"[DEBUG] Image shape: {pano_image.shape}")
            
            # Check memory footprint
            mem_mb = pano_image.nbytes / (1024 * 1024)
            print(f"[DEBUG] Image memory: {mem_mb:.1f} MB")
            
            gpsonly_exif = PIL.Image.Exif()
            gpsonly_exif[PIL.ExifTags.IFD.GPSInfo] = pano_exif.get_ifd(
                PIL.ExifTags.IFD.GPSInfo
            )

            pano_height, pano_width, *_ = pano_image.shape
            print(f"[DEBUG] pano_width: {pano_width}, pano_height: {pano_height}")
            if pano_width != pano_height * 2:
                print("[DEBUG] Image is not a 360° panorama (width != 2 * height)")
                raise ValueError("Only 360° panoramas are supported.")

            with self._lock:
                if self._camera is None:  # First image, precompute rays once.
                    print("[DEBUG] Creating virtual camera and precomputing rays...")
                    self._camera = create_virtual_camera(
                        pano_width=pano_width,
                        pano_height=pano_height,
                        hfov_deg=self.render_options.hfov_deg,
                        vfov_deg=self.render_options.vfov_deg,
                    )
                    print(f"[DEBUG] Virtual camera size: {self._camera.width}x{self._camera.height}")
                    for rig_camera in self.rig_config.cameras:
                        rig_camera.camera = self._camera
                    self._pano_size = (pano_width, pano_height)
                    
                    print("[DEBUG] Computing ray directions...")
                    self._rays_in_cam = get_virtual_camera_rays(self._camera)
                    rays_mb = self._rays_in_cam.nbytes / (1024 * 1024)
                    print(f"[DEBUG] Rays array: {self._rays_in_cam.shape}, {rays_mb:.1f} MB")
                    print("[DEBUG] Virtual camera and rays initialized.")
                else:  # Later images, verify consistent panoramas.
                    if (pano_width, pano_height) != self._pano_size:
                        print("[DEBUG] Panorama size mismatch.")
                        raise ValueError(
                            "Panoramas of different sizes are not supported."
                        )

            for cam_idx, cam_from_pano_r in enumerate(self.cams_from_pano_rotation):
                print(f"[DEBUG] Processing virtual camera {cam_idx}/{len(self.cams_from_pano_rotation)}...")
                
                try:
                    print(f"[DEBUG] Computing rays_in_pano (matrix multiply)...")
                    # Ensure rotation matrix is float32 for memory efficiency
                    cam_from_pano_r_f32 = cam_from_pano_r.astype(np.float32)
                    rays_in_pano = self._rays_in_cam @ cam_from_pano_r_f32
                    print(f"[DEBUG] rays_in_pano shape: {rays_in_pano.shape}")
                    
                    print(f"[DEBUG] Computing spherical projection...")
                    xy_in_pano = spherical_img_from_cam(self._pano_size, rays_in_pano)
                    print(f"[DEBUG] xy_in_pano shape: {xy_in_pano.shape}")
                    
                    print(f"[DEBUG] Reshaping coordinates...")
                    xy_in_pano = xy_in_pano.reshape(
                        self._camera.width, self._camera.height, 2
                    ).astype(np.float32)
                    xy_in_pano -= 0.5  # COLMAP to OpenCV pixel origin.
                    
                    print(f"[DEBUG] Remapping image for camera {cam_idx}...")
                    image = cv2.remap(
                        pano_image,
                        *np.moveaxis(xy_in_pano, [0, 1, 2], [2, 1, 0]),
                        cv2.INTER_LINEAR,
                        borderMode=cv2.BORDER_WRAP,
                    )
                    print(f"[DEBUG] Remap complete for camera {cam_idx}.")
                    
                    # We define a mask such that each pixel of the panorama has its
                    # features extracted only in a single virtual camera.
                    print(f"[DEBUG] Computing mask...")
                    closest_camera = np.argmax(
                        rays_in_pano @ self.cam_centers_in_pano.T, -1
                    )
                    print(f"[DEBUG] closest_camera shape: {closest_camera.shape}")
                    mask = (
                        ((closest_camera == cam_idx) * 255)
                        .astype(np.uint8)
                        .reshape(self._camera.width, self._camera.height)
                        .transpose()
                    )
                    print(f"[DEBUG] mask shape: {mask.shape}")

                    image_name = (
                        self.rig_config.cameras[cam_idx].image_prefix + pano_name
                    )
                    mask_name = f"{image_name}.png"

                    image_path = self.output_image_dir / image_name
                    image_path.parent.mkdir(exist_ok=True, parents=True)
                    print(f"[DEBUG] Saving image to {image_path}")
                    PIL.Image.fromarray(image).save(image_path, exif=gpsonly_exif)

                    mask_path = self.mask_dir / mask_name
                    mask_path.parent.mkdir(exist_ok=True, parents=True)
                    print(f"[DEBUG] Saving mask to {mask_path}")
                    if not pycolmap.Bitmap.from_array(mask).write(mask_path):
                        print(f"[DEBUG] Failed to write mask {mask_path}")
                        raise RuntimeError(f"Cannot write {mask_path}")
                    
                    print(f"[DEBUG] Camera {cam_idx} complete.")
                    
                except Exception as e:
                    print(f"[ERROR] Failed processing camera {cam_idx}: {type(e).__name__}: {e}")
                    import traceback
                    traceback.print_exc()
                    raise
                    
            print(f"[DEBUG] Finished processing panorama: {pano_path}")
            
        except Exception as e:
            print(f"[ERROR] Fatal error processing {pano_name}: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise


def render_perspective_images(
    pano_image_names: Sequence[str],
    pano_image_dir: Path,
    output_image_dir: Path,
    mask_dir: Path,
    render_options: PanoRenderOptions,
) -> pycolmap.RigConfig:
    """Render all panoramas into perspective images using multi-threading."""
    processor = PanoProcessor(
        pano_image_dir, output_image_dir, mask_dir, render_options
    )

    num_panos = len(pano_image_names)
    # Process single-threaded for large images to avoid memory crashes
    # Each 12288x6144 pano uses ~216MB, and creates 3072x3072 virtual cameras
    max_workers = 1  # Single-threaded to prevent memory issues with large images
    
    print(f"[DEBUG] Processing {num_panos} panoramas sequentially (single-threaded)")
    print(f"[DEBUG] Large images require sequential processing to avoid memory crashes")

    with tqdm(total=num_panos, desc="Rendering perspective images") as pbar:
        for pano_name in pano_image_names:
            try:
                processor.process(pano_name)
                pbar.update(1)
            except Exception as e:
                print(f"\n[ERROR] Failed to process {pano_name}: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                # Re-raise to stop processing
                raise

    return processor.rig_config


def load_metadata(metadata_path: Path) -> dict:
    """Load metadata JSON if available."""
    if metadata_path.exists():
        with open(metadata_path, 'r') as f:
            return json.load(f)
    return {}


def run(args):
    """Main COLMAP processing pipeline."""
    pycolmap.set_random_seed(0)

    # Define the paths.
    image_dir = args.output_path / "images"
    mask_dir = args.output_path / "masks"
    image_dir.mkdir(exist_ok=True, parents=True)
    mask_dir.mkdir(exist_ok=True, parents=True)

    database_path = args.output_path / "database.db"
    
    rec_path = args.output_path / "sparse"
    rec_path.mkdir(exist_ok=True, parents=True)

    # Load metadata if available
    metadata_path = args.input_image_path.parent / "metadata.json"
    metadata = load_metadata(metadata_path)
    if metadata:
        logging.info(f"Loaded metadata for {len(metadata.get('images', []))} images")

    # Search for input images.
    pano_image_dir = args.input_image_path
    pano_image_names = sorted(
        p.relative_to(pano_image_dir).as_posix()
        for p in pano_image_dir.rglob("*")
        if not p.is_dir() and p.suffix.lower() in {'.jpg', '.jpeg', '.png', '.tif', '.tiff'}
    )
    logging.info(f"Found {len(pano_image_names)} images in {pano_image_dir}.")

    if len(pano_image_names) == 0:
        logging.error("No panorama images found in input directory.")
        sys.exit(1)

    # Check if perspective images already exist
    existing_images = list(image_dir.rglob("*.jpg"))
    expected_num_images = len(pano_image_names) * len(PANO_RENDER_OPTIONS[args.pano_render_type].pitches_deg) * PANO_RENDER_OPTIONS[args.pano_render_type].num_steps_yaw
    
    if len(existing_images) >= expected_num_images:
        print(f"[RESUME] Found {len(existing_images)} existing perspective images (expected {expected_num_images})")
        print(f"[RESUME] Skipping panorama rendering phase")
        logging.info("Skipping panorama rendering - images already exist")
        
        # Still need to create rig_config for later stages
        from collections.abc import Sequence
        cams_from_pano_rotation = get_virtual_rotations(
            num_steps_yaw=PANO_RENDER_OPTIONS[args.pano_render_type].num_steps_yaw,
            pitches_deg=PANO_RENDER_OPTIONS[args.pano_render_type].pitches_deg,
        )
        rig_config = create_pano_rig_config(cams_from_pano_rotation)
        
        # Need to set camera info from first existing image
        first_img = PIL.Image.open(existing_images[0])
        pano_width = first_img.width * 4  # Reverse calculate from virtual camera
        pano_height = first_img.height * 2
        camera = create_virtual_camera(
            pano_width=pano_width,
            pano_height=pano_height,
            hfov_deg=PANO_RENDER_OPTIONS[args.pano_render_type].hfov_deg,
            vfov_deg=PANO_RENDER_OPTIONS[args.pano_render_type].vfov_deg,
        )
        for rig_camera in rig_config.cameras:
            rig_camera.camera = camera
    else:
        print(f"[INFO] Found {len(existing_images)} existing images, but need {expected_num_images}")
        print(f"[INFO] Will render all perspective images from panoramas")
        
        # Delete incomplete database if exists
        if database_path.exists():
            print(f"[INFO] Deleting incomplete database: {database_path}")
            database_path.unlink()
        
        # Render perspective images from panoramas
        rig_config = render_perspective_images(
            pano_image_names,
            pano_image_dir,
            image_dir,
            mask_dir,
            PANO_RENDER_OPTIONS[args.pano_render_type],
        )

    # Extract features
    logging.info("Extracting features...")
    print(f"[DEBUG] Starting SIFT feature extraction for {len(list(image_dir.rglob('*.jpg')))} images...")
    print(f"[DEBUG] This may take a while for large images...")
    
    # Use COLMAP CLI if available for better stability and CUDA support
    colmap_exe = shutil.which("colmap")
    if USE_COLMAP_CLI or colmap_exe:
        print(f"[DEBUG] Using COLMAP CLI with CUDA support 🎮")
        try:
            cmd = [
                "colmap", "feature_extractor",
                "--database_path", str(database_path),
                "--image_path", str(image_dir),
                "--ImageReader.mask_path", str(mask_dir),
                "--ImageReader.camera_model", "SIMPLE_PINHOLE",
                "--ImageReader.single_camera_per_folder", "1",
                "--FeatureExtraction.use_gpu", "1",
                "--FeatureExtraction.gpu_index", "0",
            ]
            print(f"[DEBUG] Running: {' '.join(cmd)}")
            print("[INFO] Feature extraction progress will be shown below:")
            result = subprocess.run(cmd, text=True)
            
            if result.returncode != 0:
                print(f"[ERROR] COLMAP feature extraction failed with code {result.returncode}")
                raise RuntimeError("Feature extraction failed")
            
            print("[DEBUG] Feature extraction completed successfully.")
        except Exception as e:
            print(f"[ERROR] Feature extraction failed: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise
    else:
        # Fallback to pycolmap if no CLI available
        print(f"[DEBUG] Using pycolmap (CPU-only)")
        try:
            sift_options = pycolmap.SiftExtractionOptions()
            sift_options.use_gpu = False
            sift_options.num_threads = min(8, os.cpu_count() or 4)
            print(f"[DEBUG] Using {sift_options.num_threads} CPU threads for feature extraction")
            
            reader_options = pycolmap.ImageReaderOptions()
            reader_options.camera_mode = pycolmap.CameraMode.PER_FOLDER
            reader_options.single_camera_per_folder = True
            
            pycolmap.extract_features(
                database_path,
                image_dir,
                sift_options=sift_options,
                image_reader_options=reader_options,
            )
            print("[DEBUG] Feature extraction completed successfully.")
        except Exception as e:
            print(f"[ERROR] Feature extraction failed: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise

    # Apply rig configuration
    print("[DEBUG] Applying rig configuration to database...")
    try:
        with pycolmap.Database.open(database_path) as db:
            pycolmap.apply_rig_config([rig_config], db)
        print("[DEBUG] Rig configuration applied successfully.")
    except Exception as e:
        print(f"[ERROR] Failed to apply rig configuration: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        raise

    # Match features
    logging.info(f"Matching features using {args.matcher} matcher...")
    print(f"[DEBUG] Starting feature matching with {args.matcher} matcher...")
    
    if USE_COLMAP_CLI or colmap_exe:
        print(f"[DEBUG] Using COLMAP CLI for feature matching with GPU 🎮")
        try:
            matcher_cmd = f"{args.matcher}_matcher"
            cmd = [
                "colmap", matcher_cmd,
                "--database_path", str(database_path),
                "--FeatureMatching.use_gpu", "1",
                "--FeatureMatching.gpu_index", "0",
            ]
            
            if args.matcher == "sequential":
                cmd.extend([
                    "--SequentialMatching.loop_detection", "true",
                    "--SequentialMatching.overlap", str(args.sequential_overlap),
                ])
            
            print(f"[DEBUG] Running: {' '.join(cmd)}")
            print("[INFO] Feature matching progress will be shown below:")
            result = subprocess.run(cmd, text=True)
            
            if result.returncode != 0:
                print(f"[ERROR] COLMAP feature matching failed with code {result.returncode}")
                raise RuntimeError("Feature matching failed")
            
            print("[DEBUG] Feature matching completed successfully.")
        except Exception as e:
            print(f"[ERROR] Feature matching failed: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise
    else:
        # Fallback to pycolmap
        print(f"[DEBUG] Using pycolmap for feature matching (CPU)")
        matching_options = pycolmap.FeatureMatchingOptions()
        matching_options.rig_verification = True
        matching_options.skip_image_pairs_in_same_frame = True
        
        try:
            if args.matcher == "sequential":
                pycolmap.match_sequential(
                    database_path,
                    pairing_options=pycolmap.SequentialPairingOptions(
                        loop_detection=True,
                        overlap=args.sequential_overlap
                    ),
                    matching_options=matching_options,
                )
            elif args.matcher == "exhaustive":
                pycolmap.match_exhaustive(
                    database_path, matching_options=matching_options
                )
            elif args.matcher == "vocabtree":
                pycolmap.match_vocabtree(
                    database_path, matching_options=matching_options
                )
            elif args.matcher == "spatial":
                pycolmap.match_spatial(database_path, matching_options=matching_options)
            else:
                logging.fatal(f"Unknown matcher: {args.matcher}")
            print("[DEBUG] Feature matching completed successfully.")
        except Exception as e:
            print(f"[ERROR] Feature matching failed: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise

    # Run incremental SfM
    logging.info("Running incremental SfM...")
    print("[DEBUG] Starting incremental Structure-from-Motion reconstruction...")
    
    if USE_COLMAP_CLI or colmap_exe:
        print(f"[DEBUG] Using COLMAP CLI for reconstruction")
        try:
            cmd = [
                "colmap", "mapper",
                "--database_path", str(database_path),
                "--image_path", str(image_dir),
                "--output_path", str(rec_path),
                "--Mapper.ba_refine_focal_length", "false",
                "--Mapper.ba_refine_principal_point", "false",
                "--Mapper.ba_refine_extra_params", "false",
            ]
            
            print(f"[DEBUG] Running: {' '.join(cmd)}")
            print("[INFO] Reconstruction progress will be shown below:")
            result = subprocess.run(cmd, text=True)
            
            if result.returncode != 0:
                print(f"[WARNING] COLMAP mapper returned code {result.returncode}")
            
            # Check if reconstruction was created
            rec_folders = list(rec_path.glob("*"))
            if len(rec_folders) > 0:
                logging.info(f"✅ Successfully created {len(rec_folders)} reconstruction(s)")
                logging.info(f"   Output directory: {args.output_path}")
                logging.info(f"   Sparse reconstruction: {rec_path}")
            else:
                logging.warning("⚠️ No reconstructions created - check image quality and overlap")
                
            print("[DEBUG] Incremental mapping completed.")
        except Exception as e:
            print(f"[ERROR] Incremental mapping failed: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise
    else:
        # Fallback to pycolmap
        print(f"[DEBUG] Using pycolmap for reconstruction")
        try:
            opts = pycolmap.IncrementalPipelineOptions(
                ba_refine_sensor_from_rig=False,
                ba_refine_focal_length=False,
                ba_refine_principal_point=False,
                ba_refine_extra_params=False,
            )
            recs = pycolmap.incremental_mapping(
                database_path, image_dir, rec_path, opts
            )
            print("[DEBUG] Incremental mapping completed.")
            
            # Log results
            for idx, rec in recs.items():
                logging.info(f"Reconstruction #{idx}: {rec.summary()}")
                
            if len(recs) > 0:
                logging.info(f"✅ Successfully created {len(recs)} reconstruction(s)")
                logging.info(f"   Output directory: {args.output_path}")
                logging.info(f"   Sparse reconstruction: {rec_path}")
            else:
                logging.warning("⚠️ No reconstructions created - check image quality and overlap")
        except Exception as e:
            print(f"[ERROR] Incremental mapping failed: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process 360 panorama images using COLMAP for Structure-from-Motion",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic processing with sequential matching
  python process_360_colmap.py --input_image_path ./panoramas --output_path ./colmap_output

  # Dense sampling for complex scenes
  python process_360_colmap.py --input ./panoramas --output ./output --pano_render_type dense

  # Exhaustive matching for small datasets
  python process_360_colmap.py --input ./panoramas --output ./output --matcher exhaustive
        """
    )
    parser.add_argument("--input_image_path", type=Path, required=True,
                       help="Directory containing 360 panorama images")
    parser.add_argument("--output_path", type=Path, required=True,
                       help="Output directory for COLMAP results")
    parser.add_argument(
        "--matcher",
        default="sequential",
        choices=["sequential", "exhaustive", "vocabtree", "spatial"],
        help="Feature matching strategy (default: sequential)"
    )
    parser.add_argument(
        "--pano_render_type",
        default="overlapping",
        choices=list(PANO_RENDER_OPTIONS.keys()),
        help="Virtual camera rendering configuration (default: overlapping)"
    )
    parser.add_argument(
        "--sequential_overlap",
        type=int,
        default=10,
        help="Sequence overlap for sequential matcher (default: 10)"
    )
    
    args = parser.parse_args()
    
    try:
        run(args)
    except Exception as e:
        logging.error(f"Processing failed: {e}")
        sys.exit(1)
