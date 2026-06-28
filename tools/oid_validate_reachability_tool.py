# =============================================================================
# 🔎 Validate OID ImagePath Reachability (tools/oid_validate_reachability_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          OIDValidateReachabilityTool
# Toolbox Context:    rmi_360_oid_maintenance.pyt
# Version:            0.1.0 (scaffold)
# Author:             RMI Valuation, LLC
#
# Description:
#   Samples OID rows and probes whether each ImagePath resolves. For legacy/public
#   rows this HTTP HEADs the URL. For secured rows a true end-to-end serve check is
#   not yet possible (Esri Case 04187998); as a conservative proxy it confirms the
#   underlying object key exists in the secured bucket. Read-only.
#
#   Built to produce concrete, per-image evidence while debugging secured-storage
#   serving with Esri.
#
# Core Utils:
#   - utils/shared/oid_storage_migration.py  (validate_imagepath_reachability)
#   - utils/manager/config_manager.py
# =============================================================================

import arcpy

from utils.manager.config_manager import ConfigManager
from utils.shared.oid_storage_migration import validate_imagepath_reachability


class OIDValidateReachabilityTool:
    def __init__(self):
        self.label = "20 - Validate ImagePath Reachability"
        self.description = (
            "Samples OID rows and probes that each ImagePath resolves (HTTP HEAD for "
            "public URLs; secured-bucket key existence for virtual-cache paths)."
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

        sample_param = arcpy.Parameter(
            displayName="Sample Size",
            name="sample",
            datatype="GPLong",
            parameterType="Optional",
            direction="Input",
        )
        sample_param.value = 10

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

        return [oid_param, sample_param, mode_param, project_param, config_param]

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

        try:
            sample = int(p.get("sample") or 10)
        except (TypeError, ValueError):
            sample = 10

        result = validate_imagepath_reachability(
            cfg=cfg,
            oid_fc=p["oid_fc"],
            logger=logger,
            sample=sample,
            secured_mode=secured_mode,
        )

        for image_path, reason in result.failures:
            logger.warning(f"UNREACHABLE: {image_path}  ({reason})", indent=3)

        if result.failed:
            logger.warning(
                f"{result.failed}/{result.sampled} sampled ImagePaths failed to resolve.",
                indent=2,
            )
        else:
            logger.success(f"All {result.sampled} sampled ImagePaths resolved.", indent=2)
