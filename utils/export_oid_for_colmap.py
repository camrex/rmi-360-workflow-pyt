# =============================================================================
# 📦 Export OID Points for COLMAP Processing (utils/export_oid_for_colmap.py)
# -----------------------------------------------------------------------------
# Purpose:             Exports selected OID points and their 360 images for COLMAP/Gaussian Splat processing
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-11-27
# Last Updated:        2025-11-27
#
# Description:
#   Exports 360 panorama images from selected OID feature class points to a structured
#   directory for COLMAP Structure-from-Motion processing and Gaussian Splatting.
#   Handles both local file paths and S3 URIs, preserving GPS and orientation metadata.
#
# File Location:        /utils/export_oid_for_colmap.py
# Called By:            tools/export_oid_for_colmap_tool.py
# Int. Dependencies:    utils/manager/config_manager, utils/shared/arcpy_utils, utils/shared/aws_utils
# Ext. Dependencies:    arcpy, boto3, json, shutil
#
# Output Structure:
#   <export_dir>/
#       ├── panoramas/              # 360 source images
#       ├── metadata.json           # Image metadata (GPS, orientation, OID mapping)
#       └── export_log.txt          # Export operation log
#
# Notes:
#   - Supports both local and S3 image sources
#   - Preserves EXIF GPS and orientation metadata
#   - Creates metadata JSON for downstream COLMAP processing
#   - Validates disk space before export
# =============================================================================

__all__ = ["export_oid_for_colmap"]

import arcpy
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urlparse
import urllib.request
import yaml

from utils.manager.config_manager import ConfigManager
from utils.shared.arcpy_utils import validate_fields_exist
from utils.shared.aws_utils import get_boto3_session


def _is_s3_uri(path: str) -> bool:
    """Check if path is an S3 URI (s3://)."""
    return path.lower().startswith("s3://")


def _is_http_url(path: str) -> bool:
    """Check if path is an HTTP/HTTPS URL."""
    return path.lower().startswith(("http://", "https://"))


def _load_oid_field_registry() -> Dict[str, str]:
    """
    Load OID field registry and create mapping from standard names to actual field names.
    
    Returns:
        Dict mapping standard field names (e.g., 'CamHeading') to registry names (e.g., 'CameraHeading')
    """
    registry_path = Path(__file__).parent.parent / "configs" / "esri_oid_fields_registry.yaml"
    
    try:
        with open(registry_path, 'r') as f:
            registry = yaml.safe_load(f)
        
        # Create mapping from common shorthand to registry field names
        field_mapping = {}
        for key, field_def in registry.items():
            if isinstance(field_def, dict) and 'name' in field_def:
                field_mapping[key] = field_def['name']
        
        # Add common aliases
        field_mapping['CamHeading'] = field_mapping.get('CameraHeading', 'CameraHeading')
        field_mapping['CamPitch'] = field_mapping.get('CameraPitch', 'CameraPitch')
        field_mapping['CamRoll'] = field_mapping.get('CameraRoll', 'CameraRoll')
        field_mapping['NearDist'] = field_mapping.get('NearDistance', 'NearDistance')
        field_mapping['FarDist'] = field_mapping.get('FarDistance', 'FarDistance')
        field_mapping['AvgHeight'] = field_mapping.get('AverageHeight', 'AverageHeight')
        
        return field_mapping
        
    except Exception as e:
        # Return default mapping if registry can't be loaded
        return {
            'ImagePath': 'ImagePath',
            'Name': 'Name',
            'X': 'X',
            'Y': 'Y',
            'CamHeading': 'CameraHeading',
            'CamPitch': 'CameraPitch',
            'CamRoll': 'CameraRoll',
            'NearDist': 'NearDistance',
            'FarDist': 'FarDistance',
            'HFOV': 'HorizontalFieldOfView',
            'VFOV': 'VerticalFieldOfView',
            'AvgHeight': 'AverageHeight'
        }


def _parse_s3_uri(s3_uri: str) -> Tuple[str, str]:
    """Parse S3 URI into bucket and key."""
    parsed = urlparse(s3_uri)
    bucket = parsed.netloc
    key = parsed.path.lstrip('/')
    return bucket, key


def _download_from_s3(s3_uri: str, local_path: Path, cfg: ConfigManager) -> bool:
    """
    Download a file from S3 to local path.
    
    Args:
        s3_uri: S3 URI (s3://bucket/key)
        local_path: Local destination path
        cfg: ConfigManager instance for AWS credentials
        
    Returns:
        True if download successful, False otherwise
    """
    logger = cfg.get_logger()
    try:
        bucket, key = _parse_s3_uri(s3_uri)
        session = get_boto3_session(cfg)
        s3_client = session.client('s3')
        
        # Ensure parent directory exists
        local_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Download file
        s3_client.download_file(bucket, key, str(local_path))
        return True
        
    except Exception as e:
        logger.error(f"Failed to download {s3_uri}: {e}", indent=2)
        return False


def _download_from_http(http_url: str, local_path: Path, logger) -> bool:
    """
    Download a file from HTTP/HTTPS URL to local path.
    
    Args:
        http_url: HTTP/HTTPS URL
        local_path: Local destination path
        logger: Logger instance
        
    Returns:
        True if download successful, False otherwise
    """
    try:
        # Ensure parent directory exists
        local_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Download file
        urllib.request.urlretrieve(http_url, str(local_path))
        return True
        
    except Exception as e:
        logger.error(f"Failed to download {http_url}: {e}", indent=2)
        return False


def _copy_local_file(src_path: str, dest_path: Path, logger) -> bool:
    """
    Copy local file to destination.
    
    Args:
        src_path: Source file path
        dest_path: Destination file path
        logger: Logger instance
        
    Returns:
        True if copy successful, False otherwise
    """
    try:
        # Ensure parent directory exists
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy file
        shutil.copy2(src_path, dest_path)
        return True
        
    except Exception as e:
        logger.error(f"Failed to copy {src_path}: {e}", indent=2)
        return False


def _extract_image_metadata(row_dict: Dict[str, Any], cursor_fields: List[str]) -> Dict[str, Any]:
    """
    Extract relevant metadata from OID feature for COLMAP processing.
    
    Args:
        row_dict: Dictionary of field values from cursor (actual field names)
        cursor_fields: List of field names in cursor
        
    Returns:
        Metadata dictionary with GPS, orientation, and identifiers
    """
    # Create case-insensitive lookup
    row_lower = {k.lower(): v for k, v in row_dict.items()}
    
    # Map to exact field names from OID schema
    metadata = {
        "oid": row_lower.get("oid@") or row_lower.get("objectid"),
        "name": row_lower.get("name"),
        "image_path": row_lower.get("imagepath"),
        "acquisition_date": row_lower.get("acquisitiondate"),
        "camera_heading": row_lower.get("cameraheading"),
        "camera_pitch": row_lower.get("camerapitch"),
        "camera_roll": row_lower.get("cameraroll"),
        "hfov": row_lower.get("horizontalfieldofview"),
        "vfov": row_lower.get("verticalfieldofview"),
        "near_distance": row_lower.get("neardistance"),
        "far_distance": row_lower.get("fardistance"),
        "camera_height": row_lower.get("cameraheight"),  # Changed from avg_height
        "oriented_imagery_type": row_lower.get("orientedimagerytype"),
        "image_rotation": row_lower.get("imagerotation"),
        "camera_orientation": row_lower.get("cameraorientation"),
        "orientation_accuracy": row_lower.get("orientationaccuracy"),
    }
    
    # Add GPS coordinates and elevation
    if "x" in row_lower:
        metadata["x"] = row_lower["x"]
        metadata["longitude"] = row_lower["x"]
    if "y" in row_lower:
        metadata["y"] = row_lower["y"]
        metadata["latitude"] = row_lower["y"]
    if "z" in row_lower:
        metadata["z"] = row_lower["z"]
        metadata["elevation"] = row_lower["z"]
    
    # Add spatial reference
    if "srs" in row_lower and row_lower["srs"]:
        metadata["srs"] = row_lower["srs"]
    
    # Add custom project fields
    custom_fields = ["reel", "frame", "groupindex", "mp_pre", "mp_num", "rr", "join_key"]
    for field in custom_fields:
        if field in row_lower and row_lower[field] is not None:
            metadata[field] = row_lower[field]
    
    # Remove None values to keep JSON clean
    metadata = {k: v for k, v in metadata.items() if v is not None}
    
    return metadata


def _check_disk_space(export_dir: Path, estimated_size_mb: float, logger) -> bool:
    """
    Check if sufficient disk space is available.
    
    Args:
        export_dir: Export directory path
        estimated_size_mb: Estimated export size in MB
        logger: Logger instance
        
    Returns:
        True if sufficient space, False otherwise
    """
    try:
        import shutil as space_check
        stat = space_check.disk_usage(export_dir.parent if export_dir.exists() else export_dir.resolve().parents[0])
        available_gb = stat.free / (1024 ** 3)
        required_gb = estimated_size_mb / 1024
        
        if available_gb < required_gb * 1.2:  # 20% buffer
            logger.error(f"Insufficient disk space. Required: {required_gb:.2f} GB, Available: {available_gb:.2f} GB", indent=2)
            return False
        
        logger.debug(f"Disk space check: {available_gb:.2f} GB available, {required_gb:.2f} GB required")
        return True
        
    except Exception as e:
        logger.warning(f"Could not check disk space: {e}", indent=2)
        return True  # Proceed with caution


def export_oid_for_colmap(
    cfg: ConfigManager,
    oid_fc: str,
    export_dir: str,
    where_clause: Optional[str] = None,
    estimated_image_size_mb: float = 30.0
) -> Dict[str, Any]:
    """
    Export selected OID points and 360 images for COLMAP processing.
    
    Exports panorama images from an OID feature class to a structured directory,
    handling both local and S3 sources. Creates metadata JSON with GPS coordinates,
    camera orientation, and OID mappings for downstream COLMAP/Gaussian Splat processing.
    
    Args:
        cfg: ConfigManager instance
        oid_fc: Path to OID feature class
        export_dir: Output directory for exported images and metadata
        where_clause: Optional SQL where clause to filter features
        estimated_image_size_mb: Estimated average image size for disk space check
        
    Returns:
        Dictionary with export statistics:
            - total_images: Total images processed
            - successful_exports: Number of successful exports
            - failed_exports: Number of failed exports
            - export_path: Path to export directory
            - metadata_path: Path to metadata JSON file
    """
    logger = cfg.get_logger()
    logger.info("Starting OID export for COLMAP processing...", indent=0)
    
    # Setup export directory structure
    export_path = Path(export_dir)
    panoramas_dir = export_path / "panoramas"
    panoramas_dir.mkdir(parents=True, exist_ok=True)
    
    metadata_file = export_path / "metadata.json"
    log_file = export_path / "export_log.txt"
    
    # Load OID field registry for proper field name mapping
    registry_mapping = _load_oid_field_registry()
    
    # Validate required fields exist in OID feature class (case-insensitive)
    # Note: OID@ is a special arcpy token, not a real field - don't validate it
    required_fields_to_validate = ["ImagePath", "X", "Y"]
    
    # Optional fields based on actual OID schema (all lowercase)
    optional_fields = [
        "name", "acquisitiondate", "cameraheading", "camerapitch", "cameraroll",
        "horizontalfieldofview", "verticalfieldofview", "neardistance", "fardistance",
        "orientedimagerytype", "z", "srs", "cameraheight", "cameraorientation",
        "imagerotation", "orientationaccuracy", "reel", "frame", "groupindex",
        "mp_pre", "mp_num", "rr", "join_key"
    ]
    
    # Build case-insensitive field mapping (lowercase -> actual field name)
    oid_fields_list = arcpy.ListFields(oid_fc)
    field_map = {f.name.lower(): f.name for f in oid_fields_list}
    
    # Validate actual fields exist
    validate_fields_exist(oid_fc, required_fields_to_validate, logger=logger)
    
    # Build cursor field list with actual field names + OID@ token
    available_fields = ["OID@"]  # Start with OID token
    available_fields += [field_map.get(f.lower(), f) for f in required_fields_to_validate]
    available_fields += [field_map[f.lower()] for f in optional_fields if f.lower() in field_map]
    
    logger.info(f"Found {len(available_fields)} fields to export", indent=1)
    logger.debug(f"Using fields: {available_fields}")
    
    # Get feature count for progress reporting
    feature_count = int(arcpy.management.GetCount(oid_fc)[0])
    if where_clause:
        # Apply where clause to get actual count
        temp_layer = arcpy.management.MakeFeatureLayer(oid_fc, "temp_export_layer", where_clause)[0]
        feature_count = int(arcpy.management.GetCount(temp_layer)[0])
        arcpy.management.Delete(temp_layer)
    
    if feature_count == 0:
        logger.warning("No features found matching selection criteria.", indent=1)
        return {
            "total_images": 0,
            "successful_exports": 0,
            "failed_exports": 0,
            "export_path": str(export_path),
            "metadata_path": str(metadata_file)
        }
    
    logger.info(f"Found {feature_count} features to export", indent=1)
    
    # Check disk space
    estimated_total_size = feature_count * estimated_image_size_mb
    if not _check_disk_space(export_path, estimated_total_size, logger):
        raise RuntimeError("Insufficient disk space for export")
    
    # Process features
    metadata_list = []
    successful_exports = 0
    failed_exports = 0
    
    logger.info(f"Exporting {feature_count} images...", indent=1)
    
    with arcpy.da.SearchCursor(oid_fc, available_fields, where_clause=where_clause) as cursor:
        for i, row in enumerate(cursor, 1):
            # Create dict with actual field names from cursor
            row_dict = dict(zip(available_fields, row))
            # Also create case-insensitive lookup for code compatibility
            row_dict_lower = {k.lower(): v for k, v in row_dict.items()}
            image_path = row_dict_lower.get("imagepath")
            oid = row_dict_lower.get("oid@")
            
            if not image_path:
                logger.warning(f"OID {oid}: Missing ImagePath, skipping", indent=2)
                failed_exports += 1
                continue
            
            # Log first image for diagnostics
            if i == 1:
                if _is_s3_uri(image_path):
                    logger.info("Source: S3 URIs (s3://...)", indent=2)
                elif _is_http_url(image_path):
                    logger.info("Source: HTTPS URLs", indent=2)
                else:
                    logger.info("Source: Local files", indent=2)
            
            # Determine output filename
            image_name = row_dict_lower.get("name")
            if not image_name:
                # Generate name from OID and original extension
                ext = Path(image_path).suffix or ".jpg"
                image_name = f"oid_{oid}{ext}"
            else:
                # Ensure extension is preserved
                if not Path(image_name).suffix:
                    ext = Path(image_path).suffix or ".jpg"
                    image_name = f"{image_name}{ext}"
            
            dest_path = panoramas_dir / image_name
            
            # Copy or download image based on source type
            success = False
            if _is_s3_uri(image_path):
                success = _download_from_s3(image_path, dest_path, cfg)
            elif _is_http_url(image_path):
                success = _download_from_http(image_path, dest_path, logger)
            else:
                success = _copy_local_file(image_path, dest_path, logger)
            
            if success:
                # Extract and store metadata
                image_metadata = _extract_image_metadata(row_dict, available_fields)
                image_metadata["source_path"] = image_path
                image_metadata["exported_filename"] = image_name
                metadata_list.append(image_metadata)
                successful_exports += 1
            else:
                failed_exports += 1
            
            # Progress updates every 5 images or at completion
            if i % 5 == 0 or i == feature_count:
                pct = (i / feature_count) * 100
                logger.info(f"Progress: {i}/{feature_count} ({pct:.0f}%) - {successful_exports} successful, {failed_exports} failed", indent=2)
    
    # Write metadata JSON
    metadata_output = {
        "export_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_feature_class": oid_fc,
        "total_images": feature_count,
        "successful_exports": successful_exports,
        "failed_exports": failed_exports,
        "where_clause": where_clause,
        "images": metadata_list
    }
    
    with open(metadata_file, 'w') as f:
        json.dump(metadata_output, f, indent=2)
    
    logger.info("", indent=0)  # Blank line
    logger.success(f"Export Complete: {successful_exports}/{feature_count} images successful", indent=1)
    if failed_exports > 0:
        logger.warning(f"{failed_exports} images failed to export", indent=1)
    logger.info(f"Output directory: {panoramas_dir}", indent=1)
    logger.info(f"Metadata file: {metadata_file}", indent=1)
    
    # Write log file
    with open(log_file, 'w') as f:
        f.write(f"OID Export for COLMAP Processing\n")
        f.write(f"{'='*80}\n\n")
        f.write(f"Export Date: {metadata_output['export_date']}\n")
        f.write(f"Source Feature Class: {oid_fc}\n")
        f.write(f"Export Directory: {export_path}\n")
        f.write(f"Where Clause: {where_clause or 'None'}\n\n")
        f.write(f"Results:\n")
        f.write(f"  Total Images: {feature_count}\n")
        f.write(f"  Successful: {successful_exports}\n")
        f.write(f"  Failed: {failed_exports}\n\n")
        f.write(f"Output Files:\n")
        f.write(f"  Panoramas: {panoramas_dir}\n")
        f.write(f"  Metadata: {metadata_file}\n")
    
    return {
        "total_images": feature_count,
        "successful_exports": successful_exports,
        "failed_exports": failed_exports,
        "export_path": str(export_path),
        "metadata_path": str(metadata_file)
    }
