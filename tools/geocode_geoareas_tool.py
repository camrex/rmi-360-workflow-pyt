# =============================================================================
# 🌍 Geocode Geo-Areas Tool (tools/geocode_geoareas_tool.py)
# -----------------------------------------------------------------------------
# Tool Name:          GeocodeGeoAreasTool
# Toolbox Context:    rmi_360_workflow.pyt
# Version:            1.0.0
# Author:             RMI Valuation, LLC
# Created:            2025-11-02
#
# Description:
#   ArcPy Tool class that enriches corridor photo points with Place/County/State
#   and milepost-aware context using polygon containment and intelligent gap-filling.
#   Designed to run before ExifTool tagging to ensure all geographic area data
#   is available for EXIF metadata application.
#
# File Location:      /tools/geocode_geoareas_tool.py
# Core Utils:
#   - utils/geocode_geoareas.py
#   - utils/manager/config_manager.py
#
# Parameters:
#   Photos Feature Class {photos_fc} (Feature Class): Point FC containing corridor photos with mileposts
#   Places Feature Class {places_fc} (Feature Class): Polygon FC containing place boundaries
#   Counties Feature Class {counties_fc} (Feature Class): Polygon FC containing county boundaries
#   Milepost Field {mile_field} (String): Field containing milepost values (default: milepost)
#   Route ID Field {route_field} (String): Optional field for route identification
#   Processing Mode {mode} (String): Level of enrichment to perform
#   Max Gap Miles {max_gap_miles} (Double): Maximum gap distance for place bridging
#   Break Gap Miles {break_gap_miles} (Double): Gap that breaks range continuity
#   Min Points Per Range {min_points_per_range} (Long): Minimum points for valid range
#   Promote Nearest {promote_nearest} (Boolean): Promote nearest place within threshold
#   Max Nearest Miles {max_nearest_miles} (Double): Max distance for nearest promotion
#   Write Report CSV {write_report_csv} (Boolean): Generate QA report CSV
#   Report CSV Path {report_csv_path} (File): Optional custom path for report
#
# Notes:
#   - Uses Living Atlas data (cached locally) for places and counties
#   - Idempotent operation - can be re-run safely
#   - Integrates with ConfigManager for project-specific settings
# =============================================================================

import arcpy
import os
import csv
from pathlib import Path
from typing import Dict, Any, Optional

from utils.geocode_geoareas import geocode_geoareas
from utils.manager.config_manager import ConfigManager


class GeocodeGeoAreasTool:
    def __init__(self):
        self.label = "08 - Geocode Geo-Areas"
        self.description = ("Enriches corridor photos with Place/County/State context using "
                           "polygon containment and milepost-based intelligence.")
        self.canRunInBackground = True
        self.category = "Individual Tools"

    def getParameterInfo(self):
        params = []

        # Photos Feature Class
        photos_param = arcpy.Parameter(
            displayName="Photos Feature Class",
            name="photos_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input"
        )
        photos_param.description = ("Point feature class containing corridor photos with milepost data. "
                                   "Will be enriched with place/county/state information.")
        params.append(photos_param)

        # Places Feature Class
        places_param = arcpy.Parameter(
            displayName="Places Feature Class", 
            name="places_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input"
        )
        places_param.description = ("Polygon feature class containing place boundaries. "
                                   "Recommend using Esri Living Atlas data cached locally.")
        params.append(places_param)

        # Counties Feature Class
        counties_param = arcpy.Parameter(
            displayName="Counties Feature Class",
            name="counties_fc", 
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input"
        )
        counties_param.description = ("Polygon feature class containing county boundaries. "
                                     "Recommend using Esri Living Atlas data cached locally.")
        params.append(counties_param)

        # Milepost Field
        mile_field_param = arcpy.Parameter(
            displayName="Milepost Field",
            name="mile_field",
            datatype="GPString",
            parameterType="Optional",
            direction="Input"
        )
        mile_field_param.value = "milepost"
        mile_field_param.description = "Field containing milepost values for context calculation."
        params.append(mile_field_param)

        # Route ID Field
        route_field_param = arcpy.Parameter(
            displayName="Route ID Field",
            name="route_field",
            datatype="GPString", 
            parameterType="Optional",
            direction="Input"
        )
        route_field_param.description = "Optional field identifying different routes (leave blank for single route)."
        params.append(route_field_param)

        # Processing Mode
        mode_param = arcpy.Parameter(
            displayName="Processing Mode",
            name="mode",
            datatype="GPString",
            parameterType="Required",
            direction="Input"
        )
        mode_param.filter.type = "ValueList"
        mode_param.filter.list = [
            "CONTAINMENT_ONLY",
            "CONTAINMENT+MILEPOST_CONTEXT", 
            "CONTAINMENT+MILEPOST+GAP_BRIDGE",
            "CONTAINMENT+RANGES_BUILD_APPLY",
            "FULL"
        ]
        mode_param.value = "FULL"
        mode_param.description = ("Processing level: FULL includes all enrichment steps, "
                                 "other options perform subset of operations.")
        params.append(mode_param)

        # Max Gap Miles
        max_gap_param = arcpy.Parameter(
            displayName="Max Gap Miles",
            name="max_gap_miles",
            datatype="GPDouble",
            parameterType="Optional",
            direction="Input"
        )
        max_gap_param.value = 1.0
        max_gap_param.description = "Maximum gap distance (miles) for bridging between same-place anchors."
        params.append(max_gap_param)

        # Break Gap Miles  
        break_gap_param = arcpy.Parameter(
            displayName="Break Gap Miles",
            name="break_gap_miles",
            datatype="GPDouble",
            parameterType="Optional",
            direction="Input"
        )
        break_gap_param.value = 0.5
        break_gap_param.description = "Gap distance (miles) that breaks range continuity."
        params.append(break_gap_param)

        # Min Points Per Range
        min_points_param = arcpy.Parameter(
            displayName="Min Points Per Range",
            name="min_points_per_range", 
            datatype="GPLong",
            parameterType="Optional",
            direction="Input"
        )
        min_points_param.value = 2
        min_points_param.description = "Minimum number of points required for a valid place range."
        params.append(min_points_param)

        # Promote Nearest
        promote_param = arcpy.Parameter(
            displayName="Promote Nearest to Place",
            name="promote_nearest",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input"
        )
        promote_param.value = False
        promote_param.description = "Promote nearest place to actual place if within max distance threshold."
        params.append(promote_param)

        # Max Nearest Miles
        max_nearest_param = arcpy.Parameter(
            displayName="Max Nearest Miles",
            name="max_nearest_miles",
            datatype="GPDouble",
            parameterType="Optional", 
            direction="Input"
        )
        max_nearest_param.value = 2.0
        max_nearest_param.description = "Maximum distance (miles) for promoting nearest place to actual place."
        params.append(max_nearest_param)

        # Write Report CSV
        report_param = arcpy.Parameter(
            displayName="Write Report CSV",
            name="write_report_csv",
            datatype="GPBoolean",
            parameterType="Optional",
            direction="Input"
        )
        report_param.value = True
        report_param.description = "Generate QA report CSV with enrichment statistics."
        params.append(report_param)

        # Report CSV Path
        report_path_param = arcpy.Parameter(
            displayName="Report CSV Path",
            name="report_csv_path",
            datatype="DEFile",
            parameterType="Optional",
            direction="Input"
        )
        report_path_param.description = "Custom path for QA report CSV (optional, defaults to project logs folder)."
        report_path_param.filter.list = ["csv"]
        params.append(report_path_param)

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal validation."""
        # Enable/disable report path based on write report setting
        write_report = parameters[11].value  # write_report_csv
        parameters[12].enabled = bool(write_report)  # report_csv_path
        
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation."""
        # Validate milepost field exists in photos FC
        photos_fc = parameters[0].value
        mile_field = parameters[3].value
        
        if photos_fc and mile_field:
            try:
                field_names = [f.name.lower() for f in arcpy.ListFields(photos_fc)]
                if mile_field.lower() not in field_names:
                    parameters[3].setWarningMessage(
                        f"Field '{mile_field}' not found in photos feature class. "
                        "Milepost-based enrichment will be skipped."
                    )
            except:
                pass
        
        # Validate route field if specified
        route_field = parameters[4].value
        if photos_fc and route_field:
            try:
                field_names = [f.name.lower() for f in arcpy.ListFields(photos_fc)]
                if route_field.lower() not in field_names:
                    parameters[4].setWarningMessage(
                        f"Field '{route_field}' not found in photos feature class. "
                        "All photos will be treated as single route."
                    )
            except:
                pass

        return

    def execute(self, parameters, messages):
        """Execute the tool."""
        # Extract parameters
        photos_fc = parameters[0].valueAsText
        places_fc = parameters[1].valueAsText
        counties_fc = parameters[2].valueAsText
        mile_field = parameters[3].valueAsText or "milepost"
        route_field = parameters[4].valueAsText or None
        mode = parameters[5].valueAsText or "FULL"
        max_gap_miles = parameters[6].value or 1.0
        break_gap_miles = parameters[7].value or 0.5
        min_points_per_range = parameters[8].value or 2
        promote_nearest = parameters[9].value or False
        max_nearest_miles = parameters[10].value or 2.0
        write_report_csv = parameters[11].value or True
        report_csv_path = parameters[12].valueAsText or None

        # Setup logging functions
        def logger(msg: str, indent: int = 0):
            """Logger that outputs to ArcGIS messages."""
            prefix = "  " * indent
            messages.addMessage(f"{prefix}{msg}")

        def progress(percent: int, msg: str = ""):
            """Progress callback for ArcGIS."""
            if msg:
                messages.addMessage(f"[{percent}%] {msg}")

        try:
            # Determine project base for report output
            project_base = None
            if report_csv_path:
                project_base = str(Path(report_csv_path).parent)
            else:
                # Try to infer from photos FC path
                photos_path = Path(photos_fc)
                if photos_path.suffix.lower() == '.gdb':
                    project_base = str(photos_path.parent)
                else:
                    project_base = str(photos_path.parent.parent)  # Assume project/data/file.shp structure

            logger("Starting geo-areas enrichment...")
            logger(f"Photos FC: {photos_fc}")
            logger(f"Places FC: {places_fc}")
            logger(f"Counties FC: {counties_fc}")
            logger(f"Mode: {mode}")
            logger(f"Milepost field: {mile_field}")
            logger(f"Route field: {route_field or '(single route)'}")

            # Execute enrichment based on mode
            if mode == "CONTAINMENT_ONLY":
                from utils.geocode_geoareas import enrich_points_places_counties
                results = enrich_points_places_counties(photos_fc, places_fc, counties_fc, logger, progress)
                
            elif mode == "CONTAINMENT+MILEPOST_CONTEXT":
                from utils.geocode_geoareas import enrich_points_places_counties, enrich_places_by_milepost
                
                results = enrich_points_places_counties(photos_fc, places_fc, counties_fc, logger, progress)
                
                milepost_results = enrich_places_by_milepost(
                    photos_fc, mile_field, "geo_place", route_field, logger
                )
                
                # Merge results
                for key in ["mile_filled_prev", "mile_filled_next", "mile_filled_nearest"]:
                    results[key] = milepost_results.get(key, 0)
                
            elif mode == "CONTAINMENT+MILEPOST+GAP_BRIDGE":
                from utils.geocode_geoareas import (enrich_points_places_counties, 
                                                   enrich_places_by_milepost, bridge_place_gaps_by_milepost)
                
                results = enrich_points_places_counties(photos_fc, places_fc, counties_fc, logger, progress)
                
                milepost_results = enrich_places_by_milepost(
                    photos_fc, mile_field, "geo_place", route_field, logger
                )
                
                bridged_count = bridge_place_gaps_by_milepost(
                    photos_fc, mile_field, "geo_place", route_field, 
                    "geo_county", max_gap_miles, logger
                )
                
                # Merge results
                for key in ["mile_filled_prev", "mile_filled_next", "mile_filled_nearest"]:
                    results[key] = milepost_results.get(key, 0)
                results["bridged"] = bridged_count
                
            elif mode == "CONTAINMENT+RANGES_BUILD_APPLY":
                from utils.geocode_geoareas import (enrich_points_places_counties,
                                                   build_place_mile_ranges, apply_place_mile_ranges)
                
                results = enrich_points_places_counties(photos_fc, places_fc, counties_fc, logger, progress)
                
                ranges_table = build_place_mile_ranges(
                    photos_fc, mile_field, "geo_place", route_field, "geo_county",
                    break_gap_miles=break_gap_miles, min_points_per_range=min_points_per_range
                )
                
                range_updates = apply_place_mile_ranges(
                    photos_fc, ranges_table, mile_field, route_field, "geo_place"
                )
                
                results["range_updates"] = range_updates
                
                # Clean up
                if arcpy.Exists(ranges_table):
                    arcpy.Delete_management(ranges_table)
                
            else:  # FULL mode
                results = geocode_geoareas(
                    photos_fc=photos_fc,
                    places_fc=places_fc,
                    counties_fc=counties_fc,
                    mile_field=mile_field,
                    route_field=route_field,
                    max_gap_miles=max_gap_miles,
                    promote_nearest_to_actual=promote_nearest,
                    max_nearest_miles=max_nearest_miles,
                    logger=logger,
                    progress=progress
                )

            # Generate summary report
            logger("\n" + "="*50)
            logger("GEO-AREAS ENRICHMENT SUMMARY")
            logger("="*50)
            
            total_enriched = 0
            
            if results.get("place_contained", 0) > 0:
                logger(f"Places (contained): {results['place_contained']}")
                total_enriched += results['place_contained']
                
            if results.get("county_filled", 0) > 0:
                logger(f"Counties filled: {results['county_filled']}")
                
            if results.get("state_filled", 0) > 0:
                logger(f"States filled: {results['state_filled']}")
                
            if results.get("mile_filled_prev", 0) > 0:
                logger(f"Previous context filled: {results['mile_filled_prev']}")
                
            if results.get("mile_filled_next", 0) > 0:
                logger(f"Next context filled: {results['mile_filled_next']}")
                
            if results.get("mile_filled_nearest", 0) > 0:
                logger(f"Nearest context filled: {results['mile_filled_nearest']}")
                
            if results.get("bridged", 0) > 0:
                logger(f"Places bridged: {results['bridged']}")
                total_enriched += results['bridged']
                
            if results.get("range_updates", 0) > 0:
                logger(f"Range lookups: {results['range_updates']}")
                total_enriched += results['range_updates']
                
            if results.get("promoted_nearest", 0) > 0:
                logger(f"Nearest promoted: {results['promoted_nearest']}")
                total_enriched += results['promoted_nearest']
            
            logger(f"\nTotal points enriched: {total_enriched}")

            # Write CSV report if requested
            if write_report_csv:
                if not report_csv_path:
                    # Generate default path
                    if project_base:
                        logs_dir = Path(project_base) / "logs"
                        logs_dir.mkdir(exist_ok=True)
                        report_csv_path = str(logs_dir / "geocode_geoareas_report.csv")
                    else:
                        report_csv_path = "geocode_geoareas_report.csv"
                
                self._write_csv_report(results, report_csv_path, logger)
                logger(f"\nQA report written to: {report_csv_path}")

            logger("\nGeo-areas enrichment completed successfully!")

        except Exception as e:
            messages.addErrorMessage(f"Error during geo-areas enrichment: {str(e)}")
            raise

    def _write_csv_report(self, results: Dict[str, Any], csv_path: str, logger):
        """Write detailed CSV report of enrichment results."""
        try:
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Header
                writer.writerow([
                    "Category", "Count", "Example_OIDs"
                ])
                
                # Data rows
                categories = [
                    ("Places Contained", "place_contained", "place_examples"),
                    ("Counties Filled", "county_filled", "county_examples"),
                    ("States Filled", "state_filled", "state_examples"),
                    ("Previous Context", "mile_filled_prev", "prev_examples"),
                    ("Next Context", "mile_filled_next", "next_examples"),
                    ("Nearest Context", "mile_filled_nearest", "nearest_examples"),
                    ("Places Bridged", "bridged", "bridge_examples"),
                    ("Range Lookups", "range_updates", "range_examples"),
                    ("Nearest Promoted", "promoted_nearest", "promoted_examples")
                ]
                
                for category_name, count_key, examples_key in categories:
                    count = results.get(count_key, 0)
                    examples = results.get(examples_key, [])
                    examples_str = ";".join(map(str, examples[:10]))  # First 10 examples
                    
                    writer.writerow([category_name, count, examples_str])
                    
        except Exception as e:
            logger(f"Warning: Could not write CSV report: {e}")