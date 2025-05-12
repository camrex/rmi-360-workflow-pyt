# =============================================================================
# 🧬 Create OID Schema Template (tools/create_oid_template_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          CreateOIDTemplateTool
# Toolbox Context:    rmi_360_workflow.pyt
# Version:            1.0.0
# Author:             RMI Valuation, LLC
# Created:            2025-05-08
#
# Description:
#   Implements ArcPy Tool class that creates a reusable schema table for Oriented Imagery Datasets (OIDs),
#   based on the structure defined in the project configuration file. This schema is used during feature class
#   creation to ensure consistent field definitions.
#
# File Location:      /tools/create_oid_template_tool.py
# Uses:
#   - utils/build_oid_schema.py
#   - utils/config_loader.py
#   - utils/arcpy_utils.py
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/create_oid_and_schema.md
#
# Parameters:
#   - Config File {config_file} (File): Path to the project-specific YAML configuration file defining schema and paths.
#
# Notes:
#   - Generates a geodatabase table named in config["oid_schema_template"]["template"]["template_name"]
#   - Falls back to default config path if no parameter is provided
# =============================================================================

import arcpy
from utils.build_oid_schema import create_oid_schema_template
from utils.config_loader import get_default_config_path
from utils.arcpy_utils import log_message


class CreateOIDTemplateTool(object):
    def __init__(self):
        self.label = "Create OID Schema Template"
        self.description = ("Creates a reusable schema table for Oriented Imagery Datasets (OIDs) based on config.yaml "
                            "settings.")
        self.category = "Setup"

    def getParameterInfo(self):
        """
        Defines the input parameters required for the tool.
        
        Returns:
            A list containing a single required file parameter for specifying the config.yaml file.
        """
        params = []

        # Config file
        config_param = arcpy.Parameter(
            displayName="Config File",
            name="config_file",
            datatype="DEFile",
            parameterType="Required",
            direction="Input"
        )
        config_param.description = "Config.yaml file containing project-specific settings."
        params.append(config_param)

        return params

    def execute(self, parameters, messages):
        """
        Creates an OID schema template based on the provided configuration file.
        
        Uses the specified config file to generate a reusable schema table for Oriented Imagery Datasets (OIDs) and
        logs the location of the created template.
        """
        config_file = parameters[0].valueAsText or get_default_config_path()
        schema_path = create_oid_schema_template(config_file=config_file, messages=messages)
        log_message(f"✅ Template created at: {schema_path}", messages)
