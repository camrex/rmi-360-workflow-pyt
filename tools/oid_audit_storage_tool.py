# =============================================================================
# 🧾 Audit OID vs S3 (tools/oid_audit_storage_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          OIDAuditStorageTool
# Toolbox Context:    rmi_360_oid_maintenance.pyt
# Version:            0.1.0 (scaffold)
# Author:             RMI Valuation, LLC
#
# Description:
#   Reconciles a published OID against the objects in its delivery bucket. Reports
#   rows whose image is MISSING from the bucket and bucket objects with no
#   corresponding OID row (ORPHANS). Read-only; safe to run any time, and the
#   natural before/after check around a storage migration.
#
# Core Utils:
#   - utils/shared/oid_storage_migration.py  (audit_oid_vs_s3)
#   - utils/manager/config_manager.py
# =============================================================================

import arcpy

from utils.manager.config_manager import ConfigManager
from utils.shared.oid_storage_migration import audit_oid_vs_s3


class OIDAuditStorageTool:
    def __init__(self):
        self.label = "21 - Audit OID vs S3"
        self.description = (
            "Reconciles OID ImagePath keys against the delivery bucket; reports "
            "images missing from the bucket and orphaned objects. Read-only."
        )
        self.canRunInBackground = False
        self.category = "Diagnostics"

    def getParameterInfo(self):
        oid_param = arcpy.Parameter(
            displayName="Oriented Imagery Dataset",
            name="oid_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
        )

        mode_param = arcpy.Parameter(
            displayName="Mode Override",
            name="mode_override",
            datatype="GPString",
            parameterType="Optional",
            direction="Input",
        )
        mode_param.filter.type = "ValueList"
        mode_param.filter.list = ["auto", "secured", "legacy"]
        mode_param.value = "auto"

        bucket_param = arcpy.Parameter(
            displayName="Bucket Override (blank = resolve from config)",
            name="bucket_override",
            datatype="GPString",
            parameterType="Optional",
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

        return [oid_param, mode_param, bucket_param, project_param, config_param]

    def execute(self, parameters, messages):
        p = {param.name: param.valueAsText for param in parameters}

        cfg = ConfigManager.from_file(
            path=p["config_file"],  # may be None
            project_base=p["project_folder"],
            messages=messages,
        )
        logger = cfg.get_logger()

        mode = (p.get("mode_override") or "auto").strip().lower()
        secured_mode = None if mode == "auto" else (mode == "secured")
        bucket = (p.get("bucket_override") or "").strip() or None

        result = audit_oid_vs_s3(
            cfg=cfg,
            oid_fc=p["oid_fc"],
            logger=logger,
            bucket=bucket,
            secured_mode=secured_mode,
        )

        for key in result.missing_in_bucket:
            logger.warning(f"MISSING in bucket (in OID): {key}", indent=3)
        for key in result.orphans_in_bucket:
            logger.info(f"ORPHAN in bucket (not in OID): {key}", indent=3)

        if not result.missing_in_bucket and not result.orphans_in_bucket:
            logger.success(
                f"OID and bucket reconcile: {result.oid_keys} keys, no missing or orphaned objects.",
                indent=2,
            )
