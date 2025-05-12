# =============================================================================
# 🧭 Add Images to OID (tools/add_images_to_oid_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          AddImagesToOIDTool
# Toolbox Context:    rmi_360_workflow.pyt
# Version:            1.0.0
# Author:             RMI Valuation, LLC
# Created:            2025-05-08
#
# Description:
#   Implements ArcPy Tool class for adding 360° images to an existing Oriented Imagery Dataset (OID).
#   Also assigns group indices and enriches OID attributes after insertion. Uses project config
#   settings for source folders, schema enforcement, and vertical offset control.
#
# File Location:      /tools/add_images_to_oid_tool.py
# Uses:
#   - utils/add_images_to_oid_fc.py
#   - utils/assign_group_index.py
#   - utils/calculate_oid_attributes.py
#   - utils/config_loader.py
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/add_images_to_oid.md
#
# Parameters:
#   - Project Folder {project_folder} (Folder): Root folder for this Mosaic 360 imagery project.
#   - Oriented Imagery Dataset {oid_fc} (Feature Class): Existing OID feature class to which images will be added.
#   - Adjust Z (Apply Offset) {adjust_z} (Boolean): Whether to apply vertical offset to GPS elevation using config.
#   - Config File {config_file} (File): Path to YAML config file. Optional; uses default if not provided.
#
# Notes:
#   - Conditionally applies GroupIndex and orientation enrichment
#   - Overwrites output feature class if it exists (arcpy.env.overwriteOutput = True)
#   - Designed to work with pre-built schema templates
# =============================================================================

import arcpy
from utils.add_images_to_oid_fc import add_images_to_oid
from utils.calculate_oid_attributes import enrich_oid_attributes
from utils.config_loader import get_default_config_path
from utils.assign_group_index import assign_group_index


class AddImagesToOIDTool(object):
    def __init__(self):
        self.label = "03 - Add Images to OID"
        self.description = ("Adds rendered 360° images to an existing Oriented Imagery Dataset (OID) using the ArcGIS "
                            "AddImagesToOrientedImageryDataset tool.")
        self.category = "Individual Tools"

    def getParameterInfo(self):
        """
        Defines the input parameters for the AddImagesToOIDTool geoprocessing tool.
        
        Returns:
            A list of ArcPy Parameter objects specifying the required and optional inputs:
            - Project folder for organizing imagery and logs.
            - Existing Oriented Imagery Dataset feature class.
            - Optional flag to apply vertical offset to GPS elevation.
            - YAML configuration file with project settings.
        """
        params = []

        project_param = arcpy.Parameter(
            displayName="Project Folder",
            name="project_folder",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input"
        )
        project_param.description = ("Root folder for this Mosaic 360 imagery project. All imagery and logs will be "
                                     "organized under this folder.")
        params.append(project_param)

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

        # Adjust Z (optional toggle)
        adjust_z_param = arcpy.Parameter(
            displayName="Adjust Z (Apply Offset)",
            name="adjust_z",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input"
        )
        adjust_z_param.value = True  # default to True, since typically needed
        adjust_z_param.description = (
            "Whether to apply a vertical offset (Z) to GPS elevation using the formula defined in config.yaml. "
            "Disable if Mosaic Processor has already applied Z correction."
        )
        params.append(adjust_z_param)

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
        """
        Executes the tool to add 360° images to an Oriented Imagery Dataset and update its attributes.
        
        This method processes the provided parameters to add images from the specified project folder to the given OID
        feature class, assigns group indices, and enriches the OID records with additional attributes. The process uses
        project-specific settings from the configuration file and optionally applies a vertical offset to GPS elevation
        values.
        """
        project_folder = parameters[0].valueAsText
        oid_fc = parameters[1].valueAsText
        adjust_z = bool(parameters[2].value) if parameters[2].value is not None else True
        config_file = parameters[3].valueAsText or get_default_config_path()

        add_images_to_oid(
            project_folder=project_folder,
            oid_fc_path=oid_fc,
            config_file=config_file,
            messages=messages
        )

        assign_group_index(
            oid_fc_path=oid_fc,
            config_file=config_file,
            messages=messages
        )

        # Enrich added records with Z-adjusted, derived, and default fields
        enrich_oid_attributes(
            oid_fc_path=oid_fc,
            config_file=config_file,
            messages=messages,
            adjust_z=adjust_z
        )
