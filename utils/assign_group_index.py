# =============================================================================
# 🔢 Group Index Assignment Logic (utils/assign_group_index.py)
# -----------------------------------------------------------------------------
# Purpose:             Assigns cyclic GroupIndex values to OID features based on AcquisitionDate
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-05-08
#
# Description:
#   Loads features from an OID feature class, sorts by AcquisitionDate, and assigns a
#   repeating GroupIndex value (1 to N) to support scalable image display intervals
#   in ArcGIS Pro. Handles missing dates and schema validation.
#
# File Location:        /utils/assign_group_index.py
# Called By:            tools/add_images_to_oid_tool.py
# Int. Dependencies:    config_loader, arcpy_utils
# Ext. Dependencies:    arcpy, typing
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/assign_group_index.md
#
# Notes:
#   - Raises if GroupIndex field is missing or AcquisitionDate is null
# =============================================================================

__all__ = ["assign_group_index"]

import arcpy
from typing import Optional
from utils.config_loader import resolve_config
from utils.arcpy_utils import log_message


def assign_group_index(
    oid_fc_path: str,
    config: Optional[dict] = None,
    config_file: Optional[str] = None,
    messages=None,
    group_size: int = 4,
):
    """
    Assigns a cyclic group index to features in an Oriented Imagery Dataset based on acquisition date.
    
    Features are sorted by their AcquisitionDate attribute, and a repeating group index (from 1 to group_size) is
    assigned to each. This enables variable display intervals for imagery in ArcGIS Pro. Raises a RuntimeError if the
    group index field is missing, or a ValueError if any features have null AcquisitionDate values.
    
    Args:
        oid_fc_path: Path to the Oriented Imagery Dataset feature class.
        config: Optional preloaded configuration dictionary.
        config_file: Optional path to a YAML config file, used if config is not provided.
        messages: Optional ArcGIS messaging interface (e.g., from script tools) for logging.
        group_size: Number of images per group cycle (default is 4).
    """
    if not isinstance(group_size, int) or group_size <= 0:
        log_message(f"❌ Group size must be a positive integer, got {group_size}", messages, level = "error",
                    error_type = ValueError, config = config)

    config = resolve_config(
        config=config,
        config_file=config_file,
        oid_fc_path=oid_fc_path,
        messages=messages,
        tool_name="assign_group_index"
    )

    grp_idx_fields = config.get("oid_schema_template", {}).get("grp_idx_fields", {})
    field_name = grp_idx_fields.get("group_index", {}).get("name", "GroupIndex")

    log_message(f"🧭 Assigning {field_name} values to features, sorted by AcquisitionDate...", messages, config=config)

    # Ensure the field exists
    existing_fields = [f.name for f in arcpy.ListFields(oid_fc_path)]
    if field_name not in existing_fields:
        log_message(f"❌ Field '{field_name}' not found in feature class. Please ensure it is included in your schema.",
                    messages, level="error", error_type=RuntimeError, config=config)

    # Step 1: Get all AcquisitionDates with OIDs
    rows = []
    with arcpy.da.SearchCursor(oid_fc_path, ["OID@", "AcquisitionDate"]) as cursor:
        for oid, acq_date in cursor:
            rows.append((oid, acq_date))

    # Step 2: Check for null AcquisitionDates (not allowed)
    null_oids = [oid for oid, acq_date in rows if acq_date is None]
    if null_oids:
        log_message(f"{len(null_oids)} features have null AcquisitionDate values: {null_oids}", messages,
                    level="error", error_type=ValueError, config=config)

    # Step 3: Sort by AcquisitionDate
    rows.sort(key=lambda r: r[1])

    # Step 4: Compute group index (1-based)
    oid_to_index = {
        oid: (i % group_size) + 1 for i, (oid, _) in enumerate(rows)
    }

    # Step 5: Write GroupIndex values
    updated = 0
    with arcpy.da.UpdateCursor(oid_fc_path, ["OID@", field_name]) as cursor:
        for oid, _current in cursor:
            try:
                new_val = oid_to_index.get(oid)
                if new_val is not None:
                    cursor.updateRow((oid, new_val))
                    updated += 1
            except Exception as e:
                log_message(f"❌ Failed to update GroupIndex for OID {oid}: {e}", messages, level="warning",
                            config=config)

    log_message(f"✅ Assigned GroupIndex values to {updated} feature(s).", messages, config=config)
    log_message("🧠 Tip: Use GroupIndex values to control image display intervals in ArcGIS Pro:\n"
                "    - 5m = all images (no filter)\n"
                "    - 10m = GroupIndex IN (1, 3) or (2, 4)\n"
                "    - 20m = GroupIndex = 1 (or 2, 3, or 4)", messages, config=config)
