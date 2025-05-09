# =============================================================================
# 🖼️ Enhance Images (tools/enhance_images_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          EnhanceImagesTool
# Toolbox Context:    rmi_360_workflow.pyt
# Version:            1.0.0
# Author:             RMI Valuation, LLC
# Created:            2025-05-08
#
# Description:
#   Implements ArcPy Tool class for enhancing 360° images referenced in an OID feature class.
#   Applies image processing operations including white balance, contrast, saturation boost,
#   and sharpening. Supports batch multiprocessing and writes results to a configurable output mode.
#
# File Location:      /tools/enhance_images_tool.py
# Uses:
#   - utils/enhance_images.py
#   - utils/config_loader.py
#   - utils/arcpy_utils.py
#
# Documentation:
#   See: docs/TOOL_GUIDES.md and docs/tools/enhance_images.md
#
# Parameters:
#   - Oriented Imagery Dataset {oid_fc} (Feature Class): Input OID feature class containing images to enhance.
#   - Config File (optional) {config_file} (File): Path to YAML config file. Defaults to /configs/config.yaml if omitted.
#
# Notes:
#   - Performs enhancement using OpenCV with multiprocessing support
#   - Writes detailed logs and enhancement stats to project log folder
# =============================================================================

import arcpy
from utils.enhance_images import enhance_images_in_oid
from utils.config_loader import get_default_config_path
from utils.arcpy_utils import log_message


class EnhanceImagesTool:
    def __init__(self):
        """
        Initializes the EnhanceImagesTool with metadata for ArcPy geoprocessing.
        
        Sets the tool's label, description, background execution capability, and category.
        """
        self.label = "02 - Enhance Images"
        self.description = "Enhances 360 images using color correction, adaptive contrast, and sharpening."
        self.canRunInBackground = True
        self.category = "Individual Tools"

    def getParameterInfo(self):
        """
        Defines the input parameters for the Enhance Images geoprocessing tool.
        
        Returns:
            A list of ArcPy Parameter objects specifying the required Oriented Imagery Dataset
            feature class and an optional YAML configuration file for project-specific settings.
        """
        params = []

        # Oriented Imagery Dataset (OID)
        oid_param = arcpy.Parameter(
            displayName="Oriented Imagery Dataset",
            name="oid_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input"
        )
        oid_param.description = "Path to an existing OID feature class created using the schema template."
        params.append(oid_param)

        config_param = arcpy.Parameter(
            displayName="Config File (optional)",
            name="config_file",
            datatype="DEFile",
            parameterType="Optional",
            direction="Input"
        )
        config_param.description = "Path to config.yaml with project-specific settings. Defaults to config in /configs."
        config_param.filter.list = ["yaml", "yml"]
        params.append(config_param)

        return params

    def execute(self, parameters, messages):
        """
        Executes the image enhancement process for a specified Oriented Imagery Dataset.
        
        Extracts input parameters, determines the configuration file path, and invokes the image enhancement routine.
        Logs a success message upon completion or logs and raises a runtime error if an exception occurs.
        """
        oid_fc = parameters[0].valueAsText
        config_file = parameters[1].valueAsText or get_default_config_path(messages=messages)

        try:
            log_message("Starting image enhancement...", messages)
            enhance_images_in_oid(
                oid_fc_path=oid_fc,
                config_file=config_file,
                messages=messages
            )
            log_message("✅ Image enhancement completed successfully.", messages)

        except Exception as e:
            log_message(f"❌ Enhance Images Tool failed: {e}", messages, level="error", error_type=RuntimeError)
