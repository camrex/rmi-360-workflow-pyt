__all__ = ["create_oriented_imagery_dataset"]

import os
import arcpy
from typing import Optional, Union
from utils.config_loader import resolve_config
from utils.arcpy_utils import log_message
from utils.schema_paths import resolve_schema_template_paths
from utils.schema_validator import ensure_valid_oid_schema_template


def create_oriented_imagery_dataset(
        output_fc_path: str,
        spatial_reference: Optional[Union[int, arcpy.SpatialReference]] = None,
        config: Optional[dict] = None,
        config_file: Optional[str] = None,
        project_folder: Optional[str] = None,
        messages=None) -> str:
    """
    Creates an Oriented Imagery Dataset (OID) feature class at the specified path.

    This function generates a new OID feature class using a validated schema template, applying the provided or default
    spatial reference and configuration. It ensures the output does not already exist, validates the schema, and logs
    progress and errors through the configured messaging system.

    Args:
        output_fc_path: Full path where the new OID feature class will be created.
        spatial_reference: Optional. Horizontal spatial reference as a WKID (int), an arcpy.SpatialReference object,
        or None to use defaults from configuration.
        config: Optional. Configuration dictionary to override or supplement settings.
        config_file: Optional. Path to a configuration file.
        project_folder: Optional. Path to the project folder for resolving configuration.
        messages: Optional. ArcGIS UI logger for message output.

    Returns:
        The path to the created OID feature class.

    Raises:
        ValueError: If the output feature class already exists or if the spatial reference is invalid.
    """
    config = resolve_config(
        config=config,
        config_file=config_file,
        project_folder=project_folder,
        messages=messages,
        tool_name="create_oriented_imagery_dataset")

    resolved_config_file = config.get("__source__")
    paths = resolve_schema_template_paths(config)

    output_gdb, oid_name = os.path.split(output_fc_path)

    if arcpy.Exists(output_fc_path):
        log_message(f"Output feature class already exists: {output_fc_path}", messages, level="error",
                    error_type=FileExistsError, config=config)

    sr_cfg = config.get("spatial_ref", {})
    default_xy = sr_cfg.get("gcs_horizontal_wkid", 4326)
    default_z = sr_cfg.get("vcs_vertical_wkid", 5703)

    if isinstance(spatial_reference, arcpy.SpatialReference):
        sr = spatial_reference
    elif isinstance(spatial_reference, int):
        sr = arcpy.SpatialReference(spatial_reference, default_z)
    elif spatial_reference is None:
        sr = arcpy.SpatialReference(default_xy, default_z)
    else:
        log_message(f"Invalid spatial_reference: {spatial_reference}. Must be None, WKID (int), or "
                    f"arcpy.SpatialReference.", messages, level="error", error_type=ValueError, config=config)
        raise

    # ✅ Ensure schema template is valid (and rebuild it if needed)
    ensure_valid_oid_schema_template(config=config, config_file=resolved_config_file, messages=messages)

    log_message(f"Creating Oriented Imagery Dataset at {output_fc_path}...", messages, config=config)

    try:
        arcpy.oi.CreateOrientedImageryDataset(
            out_dataset_path=output_gdb,
            out_dataset_name=oid_name,
            spatial_reference=sr,
            elevation_source="DEM",
            dem="https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer",
            lod="17",
            template=[paths.output_path],
            has_z="ENABLED"
        )
    except arcpy.ExecuteError as exc:
        log_message(f"Arcpy failed while creating OID: {oid_name}: {exc}", messages, level="error",
                    error_type=RuntimeError, config=config)

    log_message(f"OID created successfully: {output_fc_path}", messages, config=config)

    return output_fc_path
