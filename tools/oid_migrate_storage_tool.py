# =============================================================================
# 🔀 Migrate OID Storage (tools/oid_migrate_storage_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          OIDMigrateStorageTool
# Toolbox Context:    rmi_360_oid_maintenance.pyt
# Version:            0.1.0 (scaffold)
# Author:             RMI Valuation, LLC
#
# Description:
#   Orchestrator that chains the migration concerns for one OID, in either
#   direction (legacy public URL <-> secured virtual cache):
#       1. sync image objects to the destination bucket   (sync_s3_objects)
#       2. rewrite ImagePaths on a *copy* of the OID       (rewrite_oid_image_paths)
#       3. audit OID rows vs destination bucket            (audit_oid_vs_s3)
#   Re-publishing the hosted service is intentionally NOT done here -- run
#   "Generate OID Service" (main workflow) against the rewritten copy, which is
#   already mode-aware via aws.secured_delivery.enabled.
#
#   Mirrors the corridor pipeline's granular-stages + orchestrator pattern.
#   Defaults to DRY RUN end to end.
#
# Core Utils:
#   - utils/shared/oid_storage_migration.py
#   - utils/manager/config_manager.py
#
# TODO(scaffold): optionally invoke generate_oid_service() on the rewritten copy
#   once secured serving is verified (Esri Case 04187998).
# =============================================================================

import os

import arcpy

from utils.manager.config_manager import ConfigManager
from utils.shared.arcpy_utils import str_to_bool
from utils.shared.oid_storage_migration import (
    audit_oid_vs_s3,
    rewrite_oid_image_paths,
    sync_s3_objects,
)
from utils.shared.oid_storage_paths import (
    resolve_oid_key_prefix,
    resolve_oid_target_bucket,
)


class OIDMigrateStorageTool:
    def __init__(self):
        self.label = "10 - Migrate OID Storage (orchestrator)"
        self.description = (
            "Chains S3 sync -> ImagePath rewrite (on a copy) -> audit, in either "
            "direction. Does not republish the service. Dry run by default."
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
            displayName="Dry Run (no S3 copy, no ImagePath writes)",
            name="dry_run",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input",
        )
        dry_run_param.value = True

        return [oid_param, direction_param, project_param, config_param, dry_run_param]

    def execute(self, parameters, messages):
        p = {param.name: param.valueAsText for param in parameters}

        cfg = ConfigManager.from_file(
            path=p["config_file"],  # may be None
            project_base=p["project_folder"],
            messages=messages,
        )
        logger = cfg.get_logger()

        dry_run = str_to_bool(p.get("dry_run", "true"))
        to_secured = p["direction"] == "legacy_to_secured"

        legacy_bucket = resolve_oid_target_bucket(cfg, secured_mode=False)
        secured_bucket = resolve_oid_target_bucket(cfg, secured_mode=True)
        source_bucket, dest_bucket = (
            (legacy_bucket, secured_bucket) if to_secured else (secured_bucket, legacy_bucket)
        )

        logger.custom(
            f"OID storage migration: {p['direction']} {'(DRY RUN)' if dry_run else ''}",
            emoji="🔀",
            indent=1,
        )

        # --- Step 1: sync objects to the destination bucket ----------------------
        logger.info("Step 1/3 - Sync image objects to destination bucket", indent=1)
        sync_s3_objects(
            cfg=cfg,
            source_bucket=source_bucket,
            dest_bucket=dest_bucket,
            logger=logger,
            prefix=resolve_oid_key_prefix(cfg),
            skip_existing=True,
            dry_run=dry_run,
        )

        # --- Step 2: rewrite ImagePaths on a COPY (keep source pristine) ----------
        logger.info("Step 2/3 - Rewrite ImagePaths on a migration copy", indent=1)
        oid_fc = p["oid_fc"]
        oid_gdb = os.path.dirname(oid_fc)
        oid_name = os.path.splitext(os.path.basename(oid_fc))[0]
        suffix = "secured" if to_secured else "legacy"
        migrated_fc = os.path.join(oid_gdb, f"{oid_name}_{suffix}")

        if not dry_run:
            if arcpy.Exists(migrated_fc):
                logger.info(f"Overwriting existing migration copy: {migrated_fc}", indent=2)
                arcpy.management.Delete(str(migrated_fc))
            arcpy.management.Copy(str(oid_fc), str(migrated_fc))
            rewrite_target = migrated_fc
        else:
            logger.info(f"Would copy {oid_name} -> {oid_name}_{suffix} then rewrite.", indent=2)
            rewrite_target = oid_fc  # dry-run rewrite reads only, writes nothing

        rewrite_oid_image_paths(
            cfg=cfg,
            oid_fc=rewrite_target,
            target_secured=to_secured,
            logger=logger,
            dry_run=dry_run,
        )

        # --- Step 3: audit destination bucket vs OID -----------------------------
        logger.info("Step 3/3 - Audit OID rows vs destination bucket", indent=1)
        audit = audit_oid_vs_s3(
            cfg=cfg,
            oid_fc=rewrite_target,
            logger=logger,
            bucket=dest_bucket,
            secured_mode=to_secured,
        )
        for key in audit.missing_in_bucket:
            logger.warning(f"Missing in destination bucket: {key}", indent=3)

        if dry_run:
            logger.warning(
                "DRY RUN complete. Re-run with Dry Run unchecked to apply, then publish "
                "the *_%s copy with Generate OID Service." % suffix,
                indent=1,
            )
        else:
            logger.success(
                f"Migration staged. Publish '{os.path.basename(migrated_fc)}' with Generate OID Service.",
                indent=1,
            )
