# =============================================================================
# 🌍 Geo-Areas to ExifTool Integration Helper (utils/geoareas_exif_integration.py)
# -----------------------------------------------------------------------------
# Purpose:             Integration helper for geo-areas enrichment with ExifTool workflow
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-11-02
#
# Description:
#   Helper functions for integrating geo-areas enrichment data with ExifTool
#   metadata tagging. Provides field mappings and tag expressions for seamless
#   integration with the existing apply_exif_metadata workflow.
#
# File Location:        /utils/geoareas_exif_integration.py
# Called By:            utils/apply_exif_metadata.py (integration), tools/geocode_geoareas_tool.py
# Int. Dependencies:    None (standalone helper)
# Ext. Dependencies:    typing
# =============================================================================

__all__ = ["get_geoareas_exif_mapping", "build_geoareas_tag_expressions", "get_geoareas_xpcomment_suffix", "should_use_geoareas"]

from typing import Dict, Any, Optional


def should_use_geoareas(config: Dict[str, Any]) -> bool:
    """
    Check if geo-areas enrichment should be used based on geocoding.method configuration.
    
    Args:
        config: Configuration dictionary containing geocoding settings
        
    Returns:
        True if geo-areas enrichment should be applied, False otherwise
        
    Note:
        Returns True for methods: "geo_areas", "both"
        Returns False for methods: "exiftool" (or any other value)
    """
    method = config.get('geocoding', {}).get('method', 'exiftool').lower()
    return method in ['geo_areas', 'both']


def get_geoareas_exif_mapping() -> Dict[str, str]:
    """
    Get field mapping from geo-areas fields to standard EXIF tags.
    
    Returns:
        Dictionary mapping EXIF tag names to geo-areas field expressions
        
    Note:
        This mapping is used when geocoding.method is "geo_areas" or "both"
        to integrate geo-areas data with ExifTool metadata workflow.
    """
    return {
        # Standard EXIF location tags
        "City": "field.geo_place",
        "State": "field.geo_state", 
        "Country": "'United States'",
        
        # XMP/IPTC-Ext location tags  
        "LocationShownCity": "field.geo_place",
        "ProvinceState": "field.geo_state",
        "CountryName": "'United States'",
        
        # Additional context tags (if supported by EXIF config)
        "County": "field.geo_county",
        "LocationCreatedCity": "field.geo_place",
        "LocationCreatedProvinceState": "field.geo_state", 
        "LocationCreatedCountryName": "'United States'"
    }


def build_geoareas_tag_expressions(
    existing_tags: Dict[str, Any],
    include_context: bool = True,
    override_existing: bool = False
) -> Dict[str, Any]:
    """
    Build tag expressions that integrate geo-areas data with existing EXIF tags.
    
    Args:
        existing_tags: Existing EXIF tag configuration
        include_context: Whether to include milepost context in comments
        override_existing: Whether to override existing location tags
        
    Returns:
        Updated tag expressions dictionary
    """
    # Start with existing tags
    updated_tags = existing_tags.copy() if existing_tags else {}
    
    # Get geo-areas mapping
    geoareas_mapping = get_geoareas_exif_mapping()
    
    # Add or update location tags
    for tag_name, field_expr in geoareas_mapping.items():
        if override_existing or tag_name not in updated_tags:
            updated_tags[tag_name] = field_expr
    
    # Enhanced XPComment with geo-areas context
    if include_context:
        # Build context-aware comment expression
        base_comment = updated_tags.get("XPComment", "")
        
        if base_comment:
            # Append geo-areas context to existing comment
            updated_tags["XPComment"] = [
                base_comment,
                "get_geoareas_xpcomment_suffix(row)"
            ]
        else:
            # Create new comment with geo-areas context
            updated_tags["XPComment"] = "get_geoareas_xpcomment_suffix(row)"
    
    return updated_tags


def get_geoareas_xpcomment_suffix(row: Any) -> str:
    """
    Generate XPComment suffix with geo-areas context information.
    
    Args:
        row: Database cursor row with geo-areas fields
        
    Returns:
        Formatted suffix string for XPComment
    """
    try:
        # Extract geo-areas fields (assuming standard field order)
        # This would need to match the actual field order from the cursor
        geo_place = getattr(row, 'geo_place', None)
        geo_nearest_place = getattr(row, 'geo_nearest_place', None)
        geo_nearest_dir = getattr(row, 'geo_nearest_dir', None) 
        geo_nearest_miles = getattr(row, 'geo_nearest_miles', None)
        
        # Build context suffix
        if geo_place:
            # Has a place, no additional context needed
            return ""
        elif geo_nearest_place and geo_nearest_miles is not None:
            # No direct place, but has nearest context
            direction = geo_nearest_dir or "near"
            if direction in ["UP", "DN"]:
                dir_text = f"{direction} {geo_nearest_miles:.1f} mi"
            else:
                dir_text = f"{geo_nearest_miles:.1f} mi"
            return f" near {geo_nearest_place} ({dir_text})"
        else:
            # No place context available
            return ""
            
    except Exception:
        # Fallback for any field access issues
        return ""


def validate_geoareas_fields_available(photos_fc: str) -> Dict[str, bool]:
    """
    Check which geo-areas fields are available in the photos feature class.
    
    Args:
        photos_fc: Path to photos feature class
        
    Returns:
        Dictionary indicating availability of each geo-areas field
    """
    try:
        import arcpy
        
        # Get field names (case insensitive)
        field_names = {f.name.lower(): f.name for f in arcpy.ListFields(photos_fc)}
        
        # Check geo-areas fields
        geoareas_fields = [
            "geo_place", "geo_place_fips", "geo_county", "geo_county_fips",
            "geo_state", "geo_state_fips", "geo_place_source", "geo_place_inferred",
            "geo_prev_place", "geo_prev_miles", "geo_next_place", "geo_next_miles",
            "geo_nearest_place", "geo_nearest_miles", "geo_nearest_dir"
        ]
        
        availability = {}
        for field in geoareas_fields:
            availability[field] = field.lower() in field_names
        
        return availability
        
    except Exception:
        # Return all False if can't check
        return {field: False for field in geoareas_fields}


def get_integration_recommendations(photos_fc: str) -> Dict[str, Any]:
    """
    Get recommendations for integrating geo-areas with ExifTool workflow.
    
    Args:
        photos_fc: Path to photos feature class
        
    Returns:
        Dictionary with integration recommendations
    """
    availability = validate_geoareas_fields_available(photos_fc)
    
    recommendations = {
        "has_geoareas_data": any(availability.values()),
        "recommended_tags": {},
        "missing_fields": [],
        "integration_ready": False
    }
    
    # Check core fields
    core_fields = ["geo_place", "geo_county", "geo_state"]
    has_core = all(availability.get(field, False) for field in core_fields)
    
    if has_core:
        recommendations["integration_ready"] = True
        recommendations["recommended_tags"] = get_geoareas_exif_mapping()
    
    # Track missing fields
    for field, available in availability.items():
        if not available:
            recommendations["missing_fields"].append(field)
    
    # Context availability
    context_fields = ["geo_nearest_place", "geo_nearest_miles", "geo_nearest_dir"]
    has_context = all(availability.get(field, False) for field in context_fields)
    recommendations["has_context_data"] = has_context
    
    return recommendations


# Example usage in apply_exif_metadata.py integration:
"""
# In apply_exif_metadata.py, before building tag expressions:

from utils.geoareas_exif_integration import (
    build_geoareas_tag_expressions, 
    get_integration_recommendations
)

# Check if geo-areas data is available
integration_info = get_integration_recommendations(oid_fc)

if integration_info["integration_ready"]:
    # Integrate geo-areas tags with existing EXIF configuration
    updated_tags = build_geoareas_tag_expressions(
        existing_tags=cfg.get("metadata.tags", {}),
        include_context=True,
        override_existing=False
    )
    
    # Use updated_tags for ExifTool batch generation
    # ... rest of apply_exif_metadata logic
else:
    # Fall back to standard geocoding workflow
    # ... existing geocode_images logic
"""