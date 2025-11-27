# =============================================================================
# 📦 Export OID for COLMAP Tool (tools/export_oid_for_colmap_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          ExportOIDForCOLMAPTool
# Toolbox Context:    rmi_360_workflow.pyt
# Version:            1.0.0
# Author:             RMI Valuation, LLC
# Created:            2025-11-27
# Last Updated:       2025-11-27
#
# Description:
#   ArcPy Tool class that exports selected OID points and their 360 panorama images
#   for COLMAP Structure-from-Motion processing. Supports local and S3 image sources,
#   with optional automatic COLMAP processing via separate Python environment.
#
# File Location:      /tools/export_oid_for_colmap_tool.py
# Core Utils:
#   - utils/export_oid_for_colmap.py
#   - utils/manager/config_manager.py
#
# Documentation:
#   See: docs/colmap_setup.md and docs/colmap_workflow.md
#
# Parameters:
#   Project Folder {project_folder} (Folder): Root folder for project configuration
#   OID Feature Class {oid_fc} (Feature Class/Layer): OID with images to export
#   Export Directory {export_dir} (Folder): Output directory for exported images
#   Run COLMAP Processing {run_colmap} (Boolean): Execute COLMAP processing after export
#   COLMAP Environment {colmap_env} (String): Conda environment name for COLMAP
#   Matcher Type {matcher} (String): Feature matching strategy
#   Render Type {render_type} (String): Virtual camera rendering configuration
#   Config File (optional) {config_file} (File): Optional config.yaml for AWS credentials
#
# Notes:
#   - Accepts feature layers with selections or SQL where clauses
#   - Handles both local file paths and S3 URIs
#   - COLMAP processing requires separate conda environment with pycolmap
#   - See docs/colmap_setup.md for environment setup instructions
# =============================================================================

import arcpy
import os
import subprocess
import sys
from pathlib import Path

from utils.export_oid_for_colmap import export_oid_for_colmap
from utils.manager.config_manager import ConfigManager


class ExportOIDForCOLMAPTool:
    def __init__(self):
        self.label = "19 - Export OID for COLMAP"
        self.description = ("Exports selected OID points and 360 images for COLMAP/Gaussian Splat processing. "
                          "Supports local and S3 sources with optional COLMAP processing.")
        self.canRunInBackground = False
        self.category = "Individual Tools"

    def getParameterInfo(self):
        params = []

        # Project Folder
        project_param = arcpy.Parameter(
            displayName="Project Folder",
            name="project_folder",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input"
        )
        project_param.description = ("Root folder for this project. Used to load configuration for AWS credentials "
                                     "if images are stored in S3.")
        params.append(project_param)

        # OID Feature Class/Layer
        oid_param = arcpy.Parameter(
            displayName="Oriented Imagery Feature Class",
            name="oid_fc",
            datatype=["DEFeatureClass", "GPFeatureLayer"],
            parameterType="Required",
            direction="Input"
        )
        oid_param.description = ("The Oriented Imagery Dataset to export. Can be a feature class or layer with "
                                "selection applied.")
        params.append(oid_param)

        # Export Directory
        export_param = arcpy.Parameter(
            displayName="Export Directory",
            name="export_dir",
            datatype="DEFolder",
            parameterType="Required",
            direction="Input"
        )
        export_param.description = "Output directory for exported panorama images and metadata."
        params.append(export_param)

        # Run COLMAP Processing
        colmap_param = arcpy.Parameter(
            displayName="Run COLMAP Processing",
            name="run_colmap",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input"
        )
        colmap_param.value = False
        colmap_param.description = ("If checked, automatically runs COLMAP processing after export. "
                                   "Requires pycolmap conda environment.")
        params.append(colmap_param)

        # COLMAP Python Path
        env_param = arcpy.Parameter(
            displayName="COLMAP Python Executable",
            name="python_exe",
            datatype="GPString",
            parameterType="Optional",
            direction="Input"
        )
        env_param.value = r"E:\envs\colmap-processing\Scripts\python.exe"
        env_param.enabled = False
        params.append(env_param)

        # Matcher Type
        matcher_param = arcpy.Parameter(
            displayName="COLMAP Matcher Type",
            name="matcher",
            datatype="GPString",
            parameterType="Optional",
            direction="Input"
        )
        matcher_param.filter.type = "ValueList"
        matcher_param.filter.list = ["sequential", "exhaustive", "vocabtree", "spatial"]
        matcher_param.value = "sequential"
        matcher_param.description = "Feature matching strategy for COLMAP. Sequential is best for ordered corridor imagery."
        matcher_param.enabled = False
        params.append(matcher_param)

        # Render Type
        render_param = arcpy.Parameter(
            displayName="Virtual Camera Render Type",
            name="render_type",
            datatype="GPString",
            parameterType="Optional",
            direction="Input"
        )
        render_param.filter.type = "ValueList"
        render_param.filter.list = ["overlapping", "non-overlapping", "dense"]
        render_param.value = "overlapping"
        render_param.description = ("Virtual camera configuration: 'overlapping' for best quality, 'non-overlapping' "
                                   "for efficiency, 'dense' for complex scenes.")
        render_param.enabled = False
        params.append(render_param)

        # Config File (optional)
        config_param = arcpy.Parameter(
            displayName="Config File (optional)",
            name="config_file",
            datatype="DEFile",
            parameterType="Optional",
            direction="Input"
        )
        config_param.filter.list = ["yaml", "yml"]
        config_param.description = ("Optional configuration file for AWS credentials. Required if images are stored "
                                   "in S3. If not provided, searches project folder for config.yaml.")
        params.append(config_param)

        return params

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        # Enable/disable COLMAP parameters based on run_colmap checkbox
        run_colmap = parameters[3]  # Index 3: run_colmap
        python_exe = parameters[4]  # Index 4: python_exe
        matcher = parameters[5]     # Index 5: matcher
        render_type = parameters[6]  # Index 6: render_type

        if run_colmap.value:
            python_exe.enabled = True
            matcher.enabled = True
            render_type.enabled = True
        else:
            python_exe.enabled = False
            matcher.enabled = False
            render_type.enabled = False

    def updateMessages(self, parameters):
        # Validate export directory is writable
        export_dir = parameters[2]
        if export_dir.value:
            try:
                export_path = Path(str(export_dir.value))
                if export_path.exists() and not os.access(export_path, os.W_OK):
                    export_dir.setErrorMessage("Export directory is not writable.")
            except:
                pass

        # Validate Python executable exists and has pycolmap
        run_colmap = parameters[3]
        python_exe = parameters[4]
        if run_colmap.value and python_exe.value:
            python_path = Path(str(python_exe.value))
            if not python_path.exists():
                python_exe.setErrorMessage(f"Python executable not found: {python_path}")
            elif not python_path.name.lower() in ['python.exe', 'python3.exe', 'python']:
                python_exe.setWarningMessage("File does not appear to be a Python executable.")

    def execute(self, parameters, messages):
        project_folder = parameters[0].valueAsText
        oid_fc = parameters[1].valueAsText
        export_dir = parameters[2].valueAsText
        run_colmap = parameters[3].value
        python_exe = parameters[4].valueAsText
        matcher = parameters[5].valueAsText
        render_type = parameters[6].valueAsText
        config_file = parameters[7].valueAsText

        # Initialize ConfigManager
        cfg = ConfigManager.from_file(
            path=config_file,
            project_base=project_folder,
            messages=messages
        )
        logger = cfg.get_logger()
        
        arcpy.AddMessage("\n" + "="*80)
        arcpy.AddMessage("Export OID for COLMAP Processing")
        arcpy.AddMessage("="*80 + "\n")

        # Get where clause if feature layer has selection
        where_clause = None
        desc = arcpy.Describe(oid_fc)
        if hasattr(desc, 'FIDSet') and desc.FIDSet:
            # Feature layer with selection
            selection_count = len(desc.FIDSet.split(';'))
            logger.info(f"Processing {selection_count} selected features", indent=1)
        elif hasattr(desc, 'definitionQuery') and desc.definitionQuery:
            # Feature layer with definition query
            where_clause = desc.definitionQuery
            logger.info(f"Using definition query: {where_clause}", indent=1)
        
        # If it's a feature layer, get the underlying feature class path
        if hasattr(desc, 'catalogPath'):
            oid_fc_path = desc.catalogPath
        else:
            oid_fc_path = oid_fc

        try:
            # Export images and metadata
            result = export_oid_for_colmap(
                cfg=cfg,
                oid_fc=oid_fc,  # Pass the layer to respect selections
                export_dir=export_dir,
                where_clause=where_clause,
                estimated_image_size_mb=30.0
            )

            logger.success(f"Export completed: {result['successful_exports']}/{result['total_images']} images", indent=1)
            logger.info(f"Export directory: {result['export_path']}", indent=2)
            logger.info(f"Metadata file: {result['metadata_path']}", indent=2)

            # Run COLMAP processing if requested
            if run_colmap and result['successful_exports'] > 0:
                arcpy.AddMessage("\n" + "="*80)
                arcpy.AddMessage("Running COLMAP Processing")
                arcpy.AddMessage("="*80 + "\n")
                
                panoramas_dir = Path(export_dir) / "panoramas"
                colmap_output_dir = Path(export_dir) / "colmap_output"
                
                # Build COLMAP command
                script_path = Path(__file__).parent.parent / "scripts" / "process_360_colmap.py"
                
                cmd = [
                    python_exe,
                    str(script_path),
                    "--input_image_path", str(panoramas_dir),
                    "--output_path", str(colmap_output_dir),
                    "--matcher", matcher,
                    "--pano_render_type", render_type
                ]
                
                logger.info(f"COLMAP command: {' '.join(cmd)}", indent=1)
                logger.info("This may take several minutes depending on image count...", indent=1)
                
                # Run COLMAP subprocess
                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    
                    # Log COLMAP output
                    if result.stdout:
                        logger.info("COLMAP output:", indent=1)
                        for line in result.stdout.split('\n'):
                            if line.strip():
                                arcpy.AddMessage(f"  {line}")
                    
                    logger.success("COLMAP processing completed successfully", indent=1)
                    logger.info(f"COLMAP output directory: {colmap_output_dir}", indent=2)
                    
                except subprocess.CalledProcessError as e:
                    logger.error(f"COLMAP processing failed with exit code {e.returncode}", indent=1)
                    if e.stderr:
                        logger.error("COLMAP errors:", indent=2)
                        for line in e.stderr.split('\n'):
                            if line.strip():
                                arcpy.AddMessage(f"    {line}")
                    raise RuntimeError("COLMAP processing failed. Check that environment is set up correctly.")
                    
                except FileNotFoundError:
                    logger.error(f"Python executable not found: {python_exe}", indent=1)
                    raise RuntimeError(f"Could not find Python at {python_exe}. Check your environment configuration.")

            arcpy.AddMessage("\n" + "="*80)
            arcpy.AddMessage("Export Complete")
            arcpy.AddMessage("="*80 + "\n")
            if run_colmap:
                logger.info("Ready for Gaussian Splat training or 3D reconstruction", indent=1)
            else:
                logger.info(f"To run COLMAP manually: python scripts/process_360_colmap.py "
                          f"--input_image_path {Path(export_dir) / 'panoramas'} "
                          f"--output_path {Path(export_dir) / 'colmap_output'}", indent=1)

        except Exception as e:
            logger.error(f"Export failed: {str(e)}", indent=1)
            raise
