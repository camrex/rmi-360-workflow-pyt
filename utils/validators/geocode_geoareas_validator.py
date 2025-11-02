# =============================================================================
# 🌍 Geocode Geo-Areas Validator (utils/validators/geocode_geoareas_validator.py)
# -----------------------------------------------------------------------------
# Purpose:             Validates inputs and configuration for geocode geo-areas utility
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-11-02
#
# Description:
#   Input validation for the geo-areas enrichment utility. Validates feature classes,
#   field existence, spatial references, and parameter ranges to ensure reliable operation.
#
# File Location:        /utils/validators/geocode_geoareas_validator.py
# Called By:            utils/geocode_geoareas.py, tools/geocode_geoareas_tool.py
# Int. Dependencies:    utils/shared/arcpy_utils
# Ext. Dependencies:    arcpy, typing
# =============================================================================

__all__ = ["validate_geocode_geoareas_inputs"]

import arcpy
from typing import List, Optional, Tuple, Dict, Any

from utils.shared.arcpy_utils import validate_fields_exist


def validate_geocode_geoareas_inputs(
    photos_fc: str,
    places_fc: str,
    counties_fc: str,
    mile_field: str = "milepost",
    route_field: Optional[str] = None,
    max_gap_miles: float = 1.0,
    max_nearest_miles: float = 2.0
) -> Tuple[bool, List[str]]:
    """
    Validate inputs for geo-areas enrichment.
    
    Args:
        photos_fc: Path to photos feature class
        places_fc: Path to places feature class
        counties_fc: Path to counties feature class
        mile_field: Field containing milepost values
        route_field: Optional field containing route IDs
        max_gap_miles: Maximum gap distance for bridging
        max_nearest_miles: Maximum distance for nearest promotion
        
    Returns:
        Tuple of (is_valid, list_of_error_messages)
    """
    errors = []
    
    # Validate feature class existence
    if not arcpy.Exists(photos_fc):
        errors.append(f"Photos feature class does not exist: {photos_fc}")
    
    if not arcpy.Exists(places_fc):
        errors.append(f"Places feature class does not exist: {places_fc}")
    
    if not arcpy.Exists(counties_fc):
        errors.append(f"Counties feature class does not exist: {counties_fc}")
    
    # If any FC doesn't exist, can't do further validation
    if errors:
        return False, errors
    
    # Validate geometry types
    try:
        photos_desc = arcpy.Describe(photos_fc)
        if photos_desc.shapeType.upper() != "POINT":
            errors.append(f"Photos feature class must be Point geometry, got: {photos_desc.shapeType}")
    except Exception as e:
        errors.append(f"Could not describe photos feature class: {e}")
    
    try:
        places_desc = arcpy.Describe(places_fc)
        if places_desc.shapeType.upper() != "POLYGON":
            errors.append(f"Places feature class must be Polygon geometry, got: {places_desc.shapeType}")
    except Exception as e:
        errors.append(f"Could not describe places feature class: {e}")
    
    try:
        counties_desc = arcpy.Describe(counties_fc)
        if counties_desc.shapeType.upper() != "POLYGON":
            errors.append(f"Counties feature class must be Polygon geometry, got: {counties_desc.shapeType}")
    except Exception as e:
        errors.append(f"Could not describe counties feature class: {e}")
    
    # Validate required fields in photos FC
    try:
        photos_fields = [f.name.lower() for f in arcpy.ListFields(photos_fc)]
        
        # Check milepost field
        if mile_field.lower() not in photos_fields:
            errors.append(f"Milepost field '{mile_field}' not found in photos feature class")
        else:
            # Validate milepost field type
            mile_field_obj = next((f for f in arcpy.ListFields(photos_fc) 
                                 if f.name.lower() == mile_field.lower()), None)
            if mile_field_obj and mile_field_obj.type not in ["Double", "Single", "SmallInteger", "Integer"]:
                errors.append(f"Milepost field '{mile_field}' must be numeric, got: {mile_field_obj.type}")
        
        # Check route field if specified
        if route_field and route_field.lower() not in photos_fields:
            errors.append(f"Route field '{route_field}' not found in photos feature class")
    
    except Exception as e:
        errors.append(f"Could not validate photos feature class fields: {e}")
    
    # Validate places FC has expected fields
    try:
        places_fields = [f.name.upper() for f in arcpy.ListFields(places_fc)]
        
        # Look for name field (common variations)
        has_name_field = any(field in places_fields for field in ["NAME", "PLACE_NAME", "PLACENAME"])
        if not has_name_field:
            errors.append("Places feature class should have a name field (NAME, PLACE_NAME, or PLACENAME)")
        
        # Look for FIPS/GEOID field (optional but recommended)
        has_id_field = any(field in places_fields for field in ["GEOID", "FIPS", "PLACE_FIPS"])
        if not has_id_field:
            # Warning only, not an error
            pass
    
    except Exception as e:
        errors.append(f"Could not validate places feature class fields: {e}")
    
    # Validate counties FC has expected fields
    try:
        counties_fields = [f.name.upper() for f in arcpy.ListFields(counties_fc)]
        
        # Look for name field
        has_name_field = any(field in counties_fields for field in ["NAME", "COUNTY_NAME", "COUNTYNAME"])
        if not has_name_field:
            errors.append("Counties feature class should have a name field (NAME, COUNTY_NAME, or COUNTYNAME)")
        
        # Look for state fields
        has_state_field = any(field in counties_fields for field in ["STUSPS", "STATE_ABBR", "STATE_NAME"])
        if not has_state_field:
            errors.append("Counties feature class should have a state field (STUSPS, STATE_ABBR, or STATE_NAME)")
    
    except Exception as e:
        errors.append(f"Could not validate counties feature class fields: {e}")
    
    # Validate spatial reference compatibility
    try:
        photos_sr = arcpy.Describe(photos_fc).spatialReference
        places_sr = arcpy.Describe(places_fc).spatialReference
        counties_sr = arcpy.Describe(counties_fc).spatialReference
        
        # Check if all have spatial references
        if not photos_sr.name or photos_sr.name == "Unknown":
            errors.append("Photos feature class has undefined spatial reference")
        
        if not places_sr.name or places_sr.name == "Unknown":
            errors.append("Places feature class has undefined spatial reference")
        
        if not counties_sr.name or counties_sr.name == "Unknown":
            errors.append("Counties feature class has undefined spatial reference")
        
        # For spatial joins to work properly, coordinate systems should be compatible
        # ArcGIS will handle reprojection automatically, but warn about potential issues
        if (photos_sr.name != places_sr.name or 
            photos_sr.name != counties_sr.name):
            # This is just a warning - ArcGIS will handle reprojection
            pass
    
    except Exception as e:
        errors.append(f"Could not validate spatial references: {e}")
    
    # Validate parameter ranges
    if max_gap_miles <= 0:
        errors.append(f"Max gap miles must be positive, got: {max_gap_miles}")
    
    if max_gap_miles > 50:
        errors.append(f"Max gap miles seems too large (>{max_gap_miles}), check units")
    
    if max_nearest_miles <= 0:
        errors.append(f"Max nearest miles must be positive, got: {max_nearest_miles}")
    
    if max_nearest_miles > 100:
        errors.append(f"Max nearest miles seems too large (>{max_nearest_miles}), check units")
    
    # Validate feature class record counts
    try:
        photos_count = int(arcpy.management.GetCount(photos_fc).getOutput(0))
        if photos_count == 0:
            errors.append("Photos feature class is empty")
        elif photos_count > 1000000:
            # Warning for very large datasets
            pass
        
        places_count = int(arcpy.management.GetCount(places_fc).getOutput(0))
        if places_count == 0:
            errors.append("Places feature class is empty")
        
        counties_count = int(arcpy.management.GetCount(counties_fc).getOutput(0))
        if counties_count == 0:
            errors.append("Counties feature class is empty")
    
    except Exception as e:
        errors.append(f"Could not validate feature class record counts: {e}")
    
    return len(errors) == 0, errors


def validate_enrichment_config(config_dict: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate configuration parameters for geo-areas enrichment.
    
    Args:
        config_dict: Configuration dictionary
        
    Returns:
        Tuple of (is_valid, list_of_error_messages)
    """
    errors = []
    
    # Validate geo-areas section if present
    geo_areas_config = config_dict.get("geo_areas", {})
    
    if geo_areas_config:
        # Validate mile field
        mile_field = geo_areas_config.get("mile_field", "milepost")
        if not isinstance(mile_field, str) or not mile_field.strip():
            errors.append("geo_areas.mile_field must be a non-empty string")
        
        # Validate route field
        route_field = geo_areas_config.get("route_field")
        if route_field is not None and (not isinstance(route_field, str) or not route_field.strip()):
            errors.append("geo_areas.route_field must be a non-empty string or null")
        
        # Validate numeric parameters
        numeric_params = [
            ("max_gap_miles", 1.0),
            ("break_gap_miles", 0.5),
            ("max_nearest_miles", 2.0)
        ]
        
        for param_name, default_value in numeric_params:
            value = geo_areas_config.get(param_name, default_value)
            
            if not isinstance(value, (int, float)):
                errors.append(f"geo_areas.{param_name} must be numeric")
            elif value <= 0:
                errors.append(f"geo_areas.{param_name} must be positive")
            elif value > 100:
                errors.append(f"geo_areas.{param_name} seems too large (>{value})")
        
        # Validate integer parameters
        min_points = geo_areas_config.get("min_points_per_range", 2)
        if not isinstance(min_points, int):
            errors.append("geo_areas.min_points_per_range must be integer")
        elif min_points < 1:
            errors.append("geo_areas.min_points_per_range must be at least 1")
        elif min_points > 100:
            errors.append("geo_areas.min_points_per_range seems too large")
        
        # Validate boolean parameters
        bool_params = ["promote_nearest_to_actual", "write_report_csv"]
        for param_name in bool_params:
            value = geo_areas_config.get(param_name)
            if value is not None and not isinstance(value, bool):
                errors.append(f"geo_areas.{param_name} must be boolean")
    
    return len(errors) == 0, errors


def check_living_atlas_fields(places_fc: str, counties_fc: str) -> Dict[str, List[str]]:
    """
    Check for expected Living Atlas field names and provide mapping suggestions.
    
    Args:
        places_fc: Path to places feature class
        counties_fc: Path to counties feature class
        
    Returns:
        Dictionary with field mapping information
    """
    mapping_info = {
        "places_fields": [],
        "counties_fields": [],
        "places_mapping": {},
        "counties_mapping": {}
    }
    
    try:
        # Check places fields
        places_fields = {f.name.upper(): f.name for f in arcpy.ListFields(places_fc)}
        mapping_info["places_fields"] = list(places_fields.values())
        
        # Common Living Atlas places field mappings
        places_field_map = {
            "NAME": ["NAME", "PLACE_NAME", "PLACENAME"],
            "GEOID": ["GEOID", "FIPS", "PLACE_FIPS", "PLACEFIPS"],
            "STATE_ABBR": ["STUSPS", "STATE_ABBR", "ST_ABBREV"],
            "STATE_NAME": ["STATE_NAME", "STATENAME"]
        }
        
        for standard_name, variations in places_field_map.items():
            for variation in variations:
                if variation in places_fields:
                    mapping_info["places_mapping"][standard_name] = places_fields[variation]
                    break
        
        # Check counties fields
        counties_fields = {f.name.upper(): f.name for f in arcpy.ListFields(counties_fc)}
        mapping_info["counties_fields"] = list(counties_fields.values())
        
        # Common Living Atlas counties field mappings
        counties_field_map = {
            "NAME": ["NAME", "COUNTY_NAME", "COUNTYNAME"],
            "GEOID": ["GEOID", "FIPS", "COUNTY_FIPS", "COUNTYFIPS"],
            "STATEFP": ["STATEFP", "STATE_FIPS", "STATEFIPS"],
            "STUSPS": ["STUSPS", "STATE_ABBR", "ST_ABBREV"],
            "STATE_NAME": ["STATE_NAME", "STATENAME"]
        }
        
        for standard_name, variations in counties_field_map.items():
            for variation in variations:
                if variation in counties_fields:
                    mapping_info["counties_mapping"][standard_name] = counties_fields[variation]
                    break
    
    except Exception as e:
        mapping_info["error"] = str(e)
    
    return mapping_info