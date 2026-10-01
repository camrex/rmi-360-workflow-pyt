# =============================================================================
# 🩹 Fix OID Elevations (tools/oid_fix_elevations_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          OIDFixElevationsTool
# Toolbox Context:    rmi_360_oid_maintenance.pyt
# Version:            1.1.0
# Author:             RMI Valuation, LLC
#
# Description:
#   Repairs an existing OID whose camera heights are not correct NAVD88: rows
#   built before the geoid conversion (ellipsoidal) get the full conversion
#   (source frame -> NAD83(2011) at the capture epoch -> GEOID18); rows converted
#   under schema 1.5.0 without the reference-frame step get Z raised by the frame
#   shift (~1 m for POLARIS/ITRF2014). The original ellipsoidal value stays in
#   Z_Ellipsoidal, the applied frame/epoch is recorded in Z_Frame, and the tool
#   optionally republishes the
#   hosted service (deleting the previous portal items first). Accepts either
#   the source OID or the published *_aws delivery copy — an *_aws input is
#   republished directly under the un-suffixed service name (no re-copy or
#   ImagePath rewrite). Fix the copy that backs the published service; the two
#   are independent datasets. The images and their S3 objects are untouched.
#   Idempotent — rows whose Z_Frame already matches the Source Frame are skipped;
#   a Z_Frame from a different frame refuses the run.
#   Defaults to DRY RUN.
#
# Core Utils:
#   - utils/fix_oid_elevations.py  (fix_oid_elevations, republish_oid_service)
#   - utils/manager/config_manager.py
# =============================================================================

import arcpy

from utils.manager.config_manager import ConfigManager
from utils.shared.arcpy_utils import str_to_bool
from utils.shared.geoid_transform import SOURCE_FRAMES
from utils.fix_oid_elevations import (
    fix_oid_elevations,
    preview_service_overwrite,
    republish_oid_service,
)


class OIDFixElevationsTool:
    def __init__(self):
        self.label = "40 - Fix OID Elevations (-> NAVD88)"
        self.description = (
            "Brings camera Z values of an existing OID to NAVD88 orthometric height: "
            "source frame -> NAD83(2011) at the capture epoch, then GEOID18. Fixes OIDs "
            "never converted and OIDs converted without the reference-frame step, records "
            "the frame in Z_Frame, and optionally republishes the hosted service "
            "(overwrite). Dry run by default."
        )
        self.canRunInBackground = False
        self.category = "Vertical Datum Repair"

    def getParameterInfo(self):
        oid_param = arcpy.Parameter(
            displayName="Oriented Imagery Dataset (source OID or published *_aws copy)",
            name="oid_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
        )

        project_param = arcpy.Parameter(
            displayName="Project Folder",
            name="project_folder",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input",
        )

        config_param = arcpy.Parameter(
            displayName="Config File",
            name="config_file",
            datatype="DEFile",
            parameterType="Optional",
            direction="Input",
        )

        # Older project configs (schema < 1.6.0) carry no source_frame; this
        # supplies it. Blank = spatial_ref.geoid_correction.source_frame.
        frame_param = arcpy.Parameter(
            displayName="Source Frame of camera heights (blank = from config; POLARIS = ITRF2014)",
            name="source_frame",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
        )
        if frame_param.filter is not None:
            frame_param.filter.type = "ValueList"
            frame_param.filter.list = list(SOURCE_FRAMES)

        dry_run_param = arcpy.Parameter(
            displayName="Dry Run (report only, no writes)",
            name="dry_run",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        dry_run_param.value = True

        republish_param = arcpy.Parameter(
            displayName="Republish Service (deletes the existing portal items, then publishes)",
            name="republish",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        republish_param.value = False

        return [oid_param, project_param, config_param, frame_param, dry_run_param, republish_param]

    def execute(self, parameters, messages):
        p = {param.name: param.valueAsText for param in parameters}

        cfg = ConfigManager.from_file(
            path=p["config_file"],  # may be None
            project_base=p["project_folder"],
            messages=messages,
            # Repairs OIDs built BEFORE the geoid fix, whose project configs are
            # usually still on an older schema (1.3.x / 1.4.0).
            require_supported_version=False,
        )
        # Bind the GP message sink so the util's log lines show in the tool dialog
        # (ConfigManager's own LogManager is created with messages=None).
        logger = cfg.get_logger(messages)

        dry_run = str_to_bool(p.get("dry_run", "true"))
        republish = str_to_bool(p.get("republish", "false"))

        result = fix_oid_elevations(
            cfg=cfg, oid_fc=p["oid_fc"], dry_run=dry_run,
            source_frame=(p.get("source_frame") or "").strip() or None,
        )
        if result is None:
            return  # hard failure already logged; nothing was written

        for oid, before, after in result.samples:
            logger.info(f"  OID {oid}: Z {before:.3f} -> {after:.3f} m", indent=3)

        if not republish:
            return
        if dry_run:
            logger.warning(
                "DRY RUN: republish skipped — preview of what it would do:", indent=1
            )
            preview_service_overwrite(cfg=cfg, oid_fc=p["oid_fc"])
            return
        republish_oid_service(cfg=cfg, oid_fc=p["oid_fc"])
