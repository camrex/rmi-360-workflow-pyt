# =============================================================================
# 🌐 Generate OID Service (tools/generate_oid_service_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          GenerateOIDService
# Toolbox Context:    rmi_360_workflow.pyt
# Version:            1.0.0
# Author:             RMI Valuation, LLC
# Created:            2025-05-08
#
# Description:
#   Implements ArcPy Tool class that publishes an Oriented Imagery Dataset (OID) as a hosted
#   feature service on ArcGIS Online. Duplicates the OID with updated S3-based ImagePaths and
#   invokes ArcGIS's GenerateServiceFromOrientedImageryDataset tool. Optionally creates a portal
#   folder if it does not exist.
#
# File Location:      /tools/generate_oid_service_tool.py
# Uses:
#   - utils/generate_oid_service.py
#   - utils/config_loader.py
#
# Documentation:
#   See: docs/TOOL_GUIDES.md and docs/tools/generate_oid_service.md
#
# Parameters:
#   - Oriented Imagery Dataset {oid_fc} (Feature Class): Existing OID feature class to be duplicated and published.
#   - Config File {config_file} (File): YAML config file containing AWS bucket, portal, and S3 path details.
#
# Notes:
#   - Automatically updates ImagePaths to public S3 URLs
#   - Attempts to create portal folder if it does not exist
#   - Requires authenticated ArcGIS Pro session with sharing privileges
# =============================================================================

import arcpy
from utils.generate_oid_service import generate_oid_service
from utils.config_loader import get_default_config_path


class GenerateOIDService(object):
    def __init__(self):
        self.label = "10 - Generate OID Service"
        self.description = "Duplicates an OID with AWS paths and publishes it as a hosted Oriented Imagery service."
        self.canRunInBackground = False
        self.category = "Individual Tools"

    def getParameterInfo(self):
        params = []

        # Oriented Imagery Dataset (OID)
        oid_param = arcpy.Parameter(
            displayName="Oriented Imagery Dataset",
            name="oid_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input"
        )
        oid_param.description = "Path to an existing OID feature class."
        params.append(oid_param)

        # Config file
        config_param = arcpy.Parameter(
            displayName="Config File",
            name="config_file",
            datatype="DEFile",
            parameterType="Optional",
            direction="Input"
        )
        config_param.description = "Config.yaml file containing project-specific settings."
        params.append(config_param)

        return params

    def execute(self, parameters, messages):
        oid_fc = parameters[0].valueAsText
        config_file = parameters[1].valueAsText or get_default_config_path()

        generate_oid_service(
            oid_fc=oid_fc,
            config_file=config_file,
            messages=messages
        )
