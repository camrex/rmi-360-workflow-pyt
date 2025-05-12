# =============================================================================
# 🏷️ Rename and Tag Images (tools/rename_and_tag_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          RenameAndTagImagesTool
# Toolbox Context:    rmi_360_workflow.pyt
# Version:            1.0.0
# Author:             RMI Valuation, LLC
# Created:            2025-05-08
#
# Description:
#   Implements ArcPy Tool class to rename images based on project metadata and EXIF/XMP tagging rules
#   defined in a YAML configuration file. Updates both filenames and embedded metadata, and optionally
#   deletes original images post-renaming.
#
# File Location:      /tools/rename_and_tag_tool.py
# Uses:
#   - utils/rename_images.py
#   - utils/apply_exif_metadata.py
#   - utils/config_loader.py
#   - utils/arcpy_utils.py
#
# Documentation:
#   See: docs_legacy/TOOL_GUIDES.md and docs_legacy/tools/rename_and_tag.md
#
# Parameters:
#   - Oriented Imagery Dataset (OID) {oid_fc} (Feature Class): The Oriented Imagery Dataset to process.
#   - Delete Original Files After Rename? {delete_originals} (Boolean): If checked, deletes the original image files after renaming.
#   - Config File {config_file} (File): Optional YAML config file defining metadata tags and naming convention.
#
# Notes:
#   - Renaming logic supports dynamic filename expression resolution
#   - EXIF metadata updates are performed using ExifTool via batch mode
# =============================================================================

import arcpy
from utils.rename_images import rename_images
from utils.apply_exif_metadata import update_metadata_from_config
from utils.arcpy_utils import log_message
from utils.config_loader import get_default_config_path


class RenameAndTagImagesTool(object):
    def __init__(self):
        self.label = "05 - Rename and Tag Images"
        self.description = (
            "Renames images based on project metadata and updates EXIF/XMP tags, "
            "using rules defined in the configuration."
        )
        self.category = "Individual Tools"

    def getParameterInfo(self):
        """
        Defines the input parameters for the Rename and Tag Images geoprocessing tool.
        
        Returns:
            A list of ArcPy Parameter objects for the oriented imagery dataset, deletion flag, and optional
            configuration file.
        """
        params = []

        oid_param = arcpy.Parameter(
            displayName="Oriented Imagery Dataset (OID)",
            name="oid_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input"
        )
        oid_param.description = "The Oriented Imagery Dataset to process."
        params.append(oid_param)

        delete_orig = arcpy.Parameter(
            displayName="Delete Original Files After Rename?",
            name="delete_originals",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input"
        )
        delete_orig.value = False
        delete_orig.description = "If checked, original image files will be deleted after renaming."
        params.append(delete_orig)

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
        Executes the image renaming and metadata tagging workflow for the specified dataset.
        
        This method renames image files and updates their EXIF/XMP metadata according to rules defined in a
        configuration file. It logs progress and results throughout the process.
        """
        oid_fc = parameters[0].valueAsText
        delete_originals = parameters[1].value
        config_file = parameters[2].valueAsText or get_default_config_path()

        log_message("--- Starting Mosaic 360 Workflow ---", messages)

        # Step 1: Rename Images
        log_message("🔁 Step 1: Renaming images...", messages)
        renamed_images = rename_images(
            oid_fc=oid_fc,
            delete_originals=delete_originals,
            config_file=config_file,
            messages=messages
        )
        log_message(f"✅ {len(renamed_images)} images processed.", messages)

        # Step 2: Update Metadata
        log_message("📝 Step 2: Updating EXIF/XMP metadata...", messages)
        update_metadata_from_config(
            oid_fc=oid_fc,
            config_file=config_file,
            messages=messages
        )

        log_message("--- Mosaic 360 Workflow Complete ---", messages)
