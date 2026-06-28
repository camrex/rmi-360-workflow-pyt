# =============================================================================
# 🔁 Rewrite OID ImagePaths (tools/oid_rewrite_imagepaths_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          OIDRewriteImagePathsTool
# Toolbox Context:    rmi_360_oid_maintenance.pyt
# Version:            0.1.0 (scaffold)
# Author:             RMI Valuation, LLC
#
# Description:
#   Rewrites every ImagePath in an OID feature class into a chosen delivery form
#   (legacy public S3 URL or secured $virtualCacheDirectory), recovering each
#   filename from whatever form the row currently holds. Idempotent. Defaults to
#   DRY RUN: reports what would change without writing.
#
#   The atomic migration primitive (concern #2 of OID storage migration). Mutates
#   the feature class in place -- point it at a copy if you need the source kept.
#
# Core Utils:
#   - utils/shared/oid_storage_migration.py  (rewrite_oid_image_paths)
#   - utils/manager/config_manager.py
# =============================================================================

import arcpy

from utils.manager.config_manager import ConfigManager
from utils.shared.arcpy_utils import str_to_bool
from utils.shared.oid_storage_migration import rewrite_oid_image_paths


class OIDRewriteImagePathsTool:
    def __init__(self):
        self.label = "01 - Rewrite OID ImagePaths"
        self.description = (
            "Rewrites OID ImagePath values between legacy public-URL and secured "
            "virtual-cache forms. Dry run by default."
        )
        self.canRunInBackground = False
        self.category = "Storage Migration"

    def getParameterInfo(self):
        oid_param = arcpy.Parameter(
            displayName="Oriented Imagery Dataset",
            name="oid_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
        )

        target_param = arcpy.Parameter(
            displayName="Target Delivery Mode",
            name="target_mode",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
        )
        target_param.filter.type = "ValueList"
        target_param.filter.list = ["secured", "legacy"]
        target_param.value = "secured"

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

        dry_run_param = arcpy.Parameter(
            displayName="Dry Run (report only, no writes)",
            name="dry_run",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        dry_run_param.value = True

        return [oid_param, target_param, project_param, config_param, dry_run_param]

    def execute(self, parameters, messages):
        p = {param.name: param.valueAsText for param in parameters}

        cfg = ConfigManager.from_file(
            path=p["config_file"],  # may be None
            project_base=p["project_folder"],
            messages=messages,
        )
        logger = cfg.get_logger()

        target_secured = p["target_mode"].strip().lower() == "secured"
        dry_run = str_to_bool(p.get("dry_run", "true"))

        result = rewrite_oid_image_paths(
            cfg=cfg,
            oid_fc=p["oid_fc"],
            target_secured=target_secured,
            logger=logger,
            dry_run=dry_run,
        )

        for old, new in result.samples:
            logger.info(f"  {old}  ->  {new}", indent=3)
        if dry_run and result.changed:
            logger.warning(
                f"DRY RUN: {result.changed} rows would change. Re-run with Dry Run unchecked to apply.",
                indent=2,
            )
