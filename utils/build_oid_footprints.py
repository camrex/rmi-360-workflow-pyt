# =============================================================================
# 🧱 OID Footprint Builder (utils/build_oid_footprints.py)
# -----------------------------------------------------------------------------
# Purpose:             Generates a footprint feature class for a given OID using ArcGIS tools
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Builds a BUFFER-style footprint for an Oriented Imagery Dataset (OID) using ArcPy’s
#   BuildOrientedImageryFootprint. Resolves spatial reference and geographic transformation
#   from the config. Outputs a new feature class alongside the input OID.
#
# File Location:        /utils/build_oid_footprints.py
# Called By:            tools/build_oid_footprints_tool.py
# Int. Dependencies:    config_loader, expression_utils, arcpy_utils
# Ext. Dependencies:    arcpy, os, typing
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/build_oid_footprints.md
#
# Notes:
#   - Restores env settings after footprint creation
#   - Warns instead of failing if footprint creation is unsuccessful
# =============================================================================

import arcpy
import os
from typing import Optional
from utils.arcpy_utils import log_message
from utils.config_loader import resolve_config
from utils.expression_utils import resolve_expression


def build_oid_footprints(
        oid_fc: str,
        config: Optional[dict] = None,
        config_file: Optional[str] = None,
        messages=None
):
    """
    Generates a BUFFER-style footprint feature class for an Oriented Imagery Dataset (OID).

    Creates a new footprint feature class from the specified OID feature class using ArcPy's
    BuildOrientedImageryFootprint tool. The output spatial reference and optional geographic
    transformation are resolved from the provided configuration dictionary or YAML file.
    Returns the full path to the created footprint feature class, or None if spatial reference
    resolution fails.

    Args:
        oid_fc: Path to the input Oriented Imagery Dataset feature class.
        config: Optional configuration dictionary specifying spatial reference and transformation.
        config_file: Optional path to a configuration YAML file, used if config is not provided.
        messages: Optional ArcGIS messaging interface (e.g., from script tools) for logging.

    Returns:
        The full path to the generated footprint feature class, or None if spatial reference
        resolution fails.

    Raises:
        FileNotFoundError: If the input OID feature class does not exist.
        Exception: If footprint creation fails for any other reason.
    """
    log_message("Starting OID footprint generation...", messages, config=config)

    if not arcpy.Exists(oid_fc):
        log_message(f"Input OID does not exist: {oid_fc}", messages, level="error", error_type=FileNotFoundError,
                    config=config)
        return None

    config = resolve_config(
        config=config,
        config_file=config_file,
        oid_fc_path=oid_fc,
        messages=messages,
        tool_name="build_oid_footprints"
    )

    # Resolve spatial reference WKID
    sr_expr = config.get("spatial_ref", {}).get("pcs_horizontal_wkid")
    if sr_expr is None:
        log_message("`spatial_ref.pcs_horizontal_wkid` missing from config.", messages, level="error",
                    error_type=KeyError, config=config)
        return None
    output_sr = None
    try:
        wkid = int(resolve_expression(sr_expr, config=config))
        output_sr = arcpy.SpatialReference(wkid)
        log_message(f"📐 Using projected coordinate system: WKID {wkid}", messages, config=config)
    except Exception as e:
        log_message(f"❌ Failed to resolve spatial_ref.pcs_horizontal_wkid: {e}", messages, level="error",
                    error_type=ValueError, config=config)

    if output_sr is None:
        return None

    # Optional geographic transformation
    transform = config.get("spatial_ref", {}).get("transformation") or None
    if transform:
        log_message(f"🌍 Applying geographic transformation: {transform}", messages, config=config)

    # Extract out_dataset_path and out_dataset_name from oid_fc
    desc = arcpy.Describe(oid_fc)
    out_dataset_path = desc.path  # Parent GDB or feature dataset
    out_dataset_name = f"{desc.baseName}_Footprint"
    output_path = os.path.join(out_dataset_path, out_dataset_name)

    # Save current env
    prev_sr = arcpy.env.outputCoordinateSystem
    prev_trans = arcpy.env.geographicTransformations

    try:
        arcpy.env.outputCoordinateSystem = output_sr
        if transform:
            arcpy.env.geographicTransformations = transform

        arcpy.oi.BuildOrientedImageryFootprint(
            in_oriented_imagery_dataset=oid_fc,
            out_dataset_path=out_dataset_path,
            out_dataset_name=out_dataset_name,
            footprint_option="BUFFER"
        )
        log_message(f"OID footprint successfully created at: {output_path}", messages, config=config)
        return output_path

    except Exception as e:
        log_message(f"Failed to build OID footprints: {e}. Footprint creation can be done post-process.", messages,
                    level="warning", config=config)
        return None

    finally:
        arcpy.env.outputCoordinateSystem = prev_sr
        arcpy.env.geographicTransformations = prev_trans
