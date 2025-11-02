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

__all__ = ["get_geoareas_exif_mapping", "build_geoareas_tag_expressions", "get_geoareas_xpcomment_suffix", "should_use_geoareas", "get_geoareas_xpkeywords_additions"]

from typing import Dict, Any, Optional, List


def _calculate_directional_context(point_milepost: float, place_milepost: float, place_name: str, config: Dict[str, Any]) -> str:
    """
    Calculate directional context based on milepost positions and railroad operational directions.
    
    Args:
        point_milepost: Milepost of the current point
        place_milepost: Milepost of the nearest place
        place_name: Name of the nearest place
        config: Configuration dictionary containing milepost directions
        
    Returns:
        Directional context string (e.g., "2.4 miles east of Sedalia")
    """
    geo_config = config.get('geo_areas', {})
    directions = geo_config.get('milepost_directions', {})
    
    increasing_dir = directions.get('increasing_direction', 'west').lower()
    decreasing_dir = directions.get('decreasing_direction', 'east').lower()
    
    # Calculate distance and direction
    distance_miles = abs(point_milepost - place_milepost)
    
    if point_milepost > place_milepost:
        # Point has higher milepost = increasing direction
        direction = increasing_dir
    else:
        # Point has lower milepost = decreasing direction  
        direction = decreasing_dir
    
    return f"{distance_miles:.1f} miles {direction} of {place_name}"



def _get_city_fallback_expression(config: Dict[str, Any]) -> str:
    """
    Generate city fallback expression based on configuration settings.
    
    Args:
        config: Configuration dictionary containing geo_areas settings
        
    Returns:
        Expression string for city field fallback logic
    """
    geo_config = config.get('geo_areas', {})
    strategy = geo_config.get('city_fallback_strategy', 'nearest_then_county')
    include_indicator = geo_config.get('include_nearest_indicator', True)
    
    if strategy == "county_only":
        return "(field.geo_place if field.geo_place else field.geo_county)"
    elif strategy == "nearest_only":
        indicator = " + ' (nearest)'" if include_indicator else ""
        return f"(field.geo_place if field.geo_place else field.nearest_place{indicator})"
    else:  # "nearest_then_county" (default)
        indicator = " + ' (nearest)'" if include_indicator else ""
        return f"(field.geo_place if field.geo_place else (field.nearest_place{indicator} if field.nearest_place else field.geo_county))"


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


def get_geoareas_xpkeywords_additions(config: Dict[str, Any]) -> List[str]:
    """
    Get additional XPKeywords to add when geo-areas enrichment is enabled.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        List of XPKeywords expressions to add to the base XPKeywords list
    """
    keywords = []
    geo_config = config.get('geo_areas', {})
    
    # Add county keyword if enabled
    if geo_config.get('include_county_keyword', True):
        keywords.append("field.geo_county + ' County'")
    
    # Add directional context for points outside places if enabled  
    if geo_config.get('include_directional_context', True):
        # Create expression that generates directional context when appropriate
        # This will only generate a value when point is outside a place but has nearest place data
        directions = geo_config.get('milepost_directions', {})
        inc_dir = directions.get('increasing_direction', 'west')
        dec_dir = directions.get('decreasing_direction', 'east')
        
        # Use prev/next distance comparison to determine direction
        # If prev is closer, point is closer to lower milepost = decreasing direction
        # If next is closer, point is closer to higher milepost = increasing direction
        directional_expr = (
            f"(str(min(field.geo_prev_miles or 999, field.geo_next_miles or 999)) + ' miles ' + "
            f"('{dec_dir}' if (field.geo_prev_miles or 999) < (field.geo_next_miles or 999) else '{inc_dir}') + ' of ' + "
            f"(field.geo_prev_place if (field.geo_prev_miles or 999) < (field.geo_next_miles or 999) else field.geo_next_place) "
            f"if not field.geo_place and ((field.geo_prev_place and field.geo_prev_miles is not None) or (field.geo_next_place and field.geo_next_miles is not None)) "
            f"else None)"
        )
        keywords.append(directional_expr)
    
    return keywords


def get_geoareas_exif_mapping(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Get field mapping from geo-areas fields to structured EXIF tags.
    
    Args:
        config: Optional configuration dictionary for fallback customization
    
    Returns:
        Dictionary with structured EXIF tag definitions for geo-areas fields
        
    Note:
        This mapping is used when geocoding.method is "geo_areas" or "both"
        to integrate geo-areas data with ExifTool metadata workflow.
        
        Fallback behavior for points outside places is configurable via
        geo_areas.city_fallback_strategy setting.
    """
    # Default fallback if no config provided
    if config is None:
        city_fallback = "(field.geo_place if field.geo_place else (field.nearest_place if field.nearest_place else field.geo_county))"
        locationshown_fallback = "(field.geo_place if field.geo_place else (field.nearest_place + ' (nearest)' if field.nearest_place else field.geo_county + ' County'))"
    else:
        city_fallback = _get_city_fallback_expression(config)
        # For LocationShownCity, always add descriptive suffixes
        geo_config = config.get('geo_areas', {})
        if geo_config.get('city_fallback_strategy') == "county_only":
            locationshown_fallback = "(field.geo_place if field.geo_place else field.geo_county + ' County')"
        elif geo_config.get('city_fallback_strategy') == "nearest_only":
            locationshown_fallback = "(field.geo_place if field.geo_place else field.nearest_place + ' (nearest)')"
        else:  # nearest_then_county
            locationshown_fallback = "(field.geo_place if field.geo_place else (field.nearest_place + ' (nearest)' if field.nearest_place else field.geo_county + ' County'))"
    
    return {
        # Standard EXIF location tags
        "City": city_fallback,
        "State": "field.geo_state", 
        "Country": "'United States'",
        "CountryCode": "'US'",
        
        # XMP IPTC Core tags
        "XMP-iptcCore": {
            "CountryCode": "'US'"
        },
        
        # XMP IPTC Extension tags  
        "XMP-iptcExt": {
            "LocationShownCity": locationshown_fallback,
            "LocationShownCountryCode": "'US'",
            "LocationShownCountryName": "'United States'",
            "LocationShownProvinceState": "field.geo_state",
            "LocationShownGPSLatitude": "field.Y",
            "LocationShownGPSLongitude": "field.X"
        },
        
        # XMP Photoshop tags
        "XMP-photoshop": {
            "City": city_fallback,
            "Country": "'United States'",
            "State": "field.geo_state"
        }
    }
    
    # Note: State FIPS can be derived from county FIPS if needed:
    # state_fips = field.geo_county_fips[:2] if field.geo_county_fips else None


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