# =============================================================================
# 🪣 Sync OID S3 Objects (tools/oid_sync_s3_objects_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          OIDSyncS3ObjectsTool
# Toolbox Context:    rmi_360_oid_maintenance.pyt
# Version:            0.1.0 (scaffold)
# Author:             RMI Valuation, LLC
#
# Description:
#   Server-side copies a project's image objects from one bucket to another,
#   preserving the key ({prefix}/{filename}). Because the key layout is identical
#   across delivery modes, this moves the image bytes between the unsecured public
#   bucket (aws.s3_bucket_panos_unsecured) and the secured bucket (aws.s3_bucket_panos_secured)
#   with no re-upload from the local machine. Defaults to DRY RUN.
#
#   Concern #1 of OID storage migration.
#
# Core Utils:
#   - utils/shared/oid_storage_migration.py  (sync_s3_objects)
#   - utils/manager/config_manager.py
# =============================================================================

import arcpy

from utils.manager.config_manager import ConfigManager
from utils.shared.arcpy_utils import str_to_bool
from utils.shared.oid_storage_migration import sync_s3_objects
from utils.shared.oid_storage_paths import (
    resolve_oid_key_prefix,
    resolve_oid_target_bucket,
)


class OIDSyncS3ObjectsTool:
    def __init__(self):
        self.label = "02 - Sync OID S3 Objects (bucket -> bucket)"
        self.description = (
            "Server-side copies a project's images between the legacy and secured "
            "buckets, key-for-key. Dry run by default."
        )
        self.canRunInBackground = False
        self.category = "Storage Migration"

    def getParameterInfo(self):
        direction_param = arcpy.Parameter(
            displayName="Direction",
            name="direction",
            datatype="GPString",
            parameterType="Required",
            direction="Input",
        )
        direction_param.filter.type = "ValueList"
        direction_param.filter.list = ["legacy_to_secured", "secured_to_legacy"]
        direction_param.value = "legacy_to_secured"

        prefix_param = arcpy.Parameter(
            displayName="Key Prefix Override (blank = resolve from config)",
            name="prefix_override",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
        )

        skip_existing_param = arcpy.Parameter(
            displayName="Skip Objects Already in Destination",
            name="skip_existing",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        skip_existing_param.value = True

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
            displayName="Dry Run (list only, no copy)",
            name="dry_run",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        dry_run_param.value = True

        return [
            direction_param,
            prefix_param,
            skip_existing_param,
            project_param,
            config_param,
            dry_run_param,
        ]

    def execute(self, parameters, messages):
        p = {param.name: param.valueAsText for param in parameters}

        cfg = ConfigManager.from_file(
            path=p["config_file"],  # may be None
            project_base=p["project_folder"],
            messages=messages,
        )
        logger = cfg.get_logger()

        legacy_bucket = resolve_oid_target_bucket(cfg, secured_mode=False)
        secured_bucket = resolve_oid_target_bucket(cfg, secured_mode=True)

        if p["direction"] == "legacy_to_secured":
            source_bucket, dest_bucket = legacy_bucket, secured_bucket
        else:
            source_bucket, dest_bucket = secured_bucket, legacy_bucket

        if not source_bucket or not dest_bucket:
            logger.error(
                "Both unsecured (aws.s3_bucket_panos_unsecured) and secured (aws.s3_bucket_panos_secured) "
                "buckets must be configured to sync.",
                error_type=ValueError,
                indent=2,
            )
            return

        prefix = (p.get("prefix_override") or "").strip() or resolve_oid_key_prefix(cfg)

        result = sync_s3_objects(
            cfg=cfg,
            source_bucket=source_bucket,
            dest_bucket=dest_bucket,
            logger=logger,
            prefix=prefix,
            skip_existing=str_to_bool(p.get("skip_existing", "true")),
            dry_run=str_to_bool(p.get("dry_run", "true")),
        )

        if result.failures:
            logger.warning(f"{len(result.failures)} object(s) failed to copy; see log above.", indent=2)
