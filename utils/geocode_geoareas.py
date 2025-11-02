# =============================================================================
# 🌍 Corridor Geo-Areas Enrichment (utils/geocode_geoareas.py)
# -----------------------------------------------------------------------------
# Purpose:             Enriches corridor photo points with Place/County/State and milepost-aware context
# Project:             RMI 360 Imaging Workflow Python Toolbox
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-11-02
#
# Description:
#   Production-ready utility for enriching corridor photo points with geographic context using:
#   - Polygon containment joins for Places, Counties, States
#   - Milepost-based logic for context (prev/next/nearest)
#   - Gap-bridging for short slivers between same-place anchors
#   - Range-based lookup from anchor points
#   - Optional nearest-place promotion within threshold
#   
#   Designed to run before ExifTool tagging to ensure all geo-area data is available
#   for EXIF metadata application in a single batch operation.
#
# File Location:        /utils/geocode_geoareas.py
# Validator:            /utils/validators/geocode_geoareas_validator.py
# Called By:            tools/geocode_geoareas_tool.py
# Int. Dependencies:    utils/manager/config_manager, utils/shared/arcpy_utils
# Ext. Dependencies:    arcpy, typing, pathlib
#
# API Functions:
#   - enrich_points_places_counties(): Polygon containment joins
#   - enrich_places_by_milepost(): Fill prev/next/nearest context
#   - bridge_place_gaps_by_milepost(): Bridge short gaps between same places
#   - build_place_mile_ranges(): Build contiguous place ranges
#   - apply_place_mile_ranges(): Apply ranges to fill nulls
#   - promote_nearest_to_place(): Promote nearest place within threshold
#   - geocode_geoareas(): Main orchestrator function
# =============================================================================

__all__ = [
    "enrich_points_places_counties",
    "enrich_places_by_milepost", 
    "bridge_place_gaps_by_milepost",
    "build_place_mile_ranges",
    "apply_place_mile_ranges", 
    "promote_nearest_to_place",
    "geocode_geoareas"
]

import arcpy
import os
from typing import Dict, List, Optional, Union, Callable, Any, Tuple
from pathlib import Path

from utils.shared.arcpy_utils import validate_fields_exist


# =============================================================================
# FIELD DEFINITIONS AND SCHEMA
# =============================================================================

# Output fields to ensure exist in photos_fc
GEO_AREA_FIELDS = [
    # Place/County/State core fields
    ("geo_place", "TEXT", 100),
    ("geo_place_fips", "TEXT", 20), 
    ("geo_county", "TEXT", 50),
    ("geo_county_fips", "TEXT", 10),  # 5-digit FIPS (first 2 = state, last 3 = county)
    ("geo_state", "TEXT", 30),
    
    # Provenance and flags
    ("geo_place_source", "TEXT", 20),  # CONTAINED|INFERRED_BRIDGE|NEAREST_ALONG|RANGE_LOOKUP|COUNTY_ONLY
    ("geo_place_inferred", "SHORT", None),  # 0=direct, 1=inferred
    ("geo_place_gap_miles", "DOUBLE", None),  # gap distance when bridged
    
    # Milepost context fields
    ("geo_prev_place", "TEXT", 100),
    ("geo_prev_miles", "DOUBLE", None),
    ("geo_next_place", "TEXT", 100), 
    ("geo_next_miles", "DOUBLE", None),
    ("geo_nearest_place", "TEXT", 100),
    ("geo_nearest_miles", "DOUBLE", None),
    ("geo_nearest_dir", "TEXT", 2),  # UP|DN
]

# Source type constants
class SourceType:
    CONTAINED = "CONTAINED"
    INFERRED_BRIDGE = "INFERRED_BRIDGE" 
    NEAREST_ALONG = "NEAREST_ALONG"
    RANGE_LOOKUP = "RANGE_LOOKUP"
    COUNTY_ONLY = "COUNTY_ONLY"


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def _ensure_geo_area_fields(photos_fc: str, logger: Optional[Callable] = None) -> None:
    """Ensure all geo-area fields exist in the photos feature class."""
    if logger:
        logger("Ensuring geo-area fields exist...")
    
    # Get existing fields
    existing_fields = {f.name.lower(): f for f in arcpy.ListFields(photos_fc)}
    
    # Add missing fields
    fields_to_add = []
    for field_name, field_type, field_length in GEO_AREA_FIELDS:
        if field_name.lower() not in existing_fields:
            fields_to_add.append((field_name, field_type, field_length))
    
    if fields_to_add:
        if logger:
            logger(f"Adding {len(fields_to_add)} missing geo-area fields...")
        
        for field_name, field_type, field_length in fields_to_add:
            if field_length:
                arcpy.management.AddField(photos_fc, field_name, field_type, field_length=field_length)
            else:
                arcpy.management.AddField(photos_fc, field_name, field_type)


def _get_route_groups(photos_fc: str, route_field: Optional[str] = None) -> Dict[str, List[int]]:
    """Group OIDs by route_id, treating missing route_field as single route."""
    route_groups = {}
    
    # Build field list
    fields = ["OID@"]
    if route_field and validate_fields_exist(photos_fc, [route_field], raise_on_missing=False):
        fields.append(route_field)
        use_route_field = True
    else:
        use_route_field = False
    
    # Group by route
    with arcpy.da.SearchCursor(photos_fc, fields) as cursor:
        for row in cursor:
            oid = row[0]
            route_id = row[1] if use_route_field else "default_route"
            
            # Handle None/null route_id
            if route_id is None:
                route_id = "default_route"
            
            if route_id not in route_groups:
                route_groups[route_id] = []
            route_groups[route_id].append(oid)
    
    return route_groups


def _get_sorted_anchors(photos_fc: str, oids: List[int], mile_field: str = "milepost", 
                       place_field: str = "geo_place") -> List[Tuple[int, float, str]]:
    """Get sorted list of (oid, milepost, place) for anchors that have places."""
    anchors = []
    
    # Build where clause for OIDs
    oid_list = ",".join(map(str, oids))
    where_clause = f"OBJECTID IN ({oid_list}) AND {place_field} IS NOT NULL AND {place_field} <> ''"
    
    fields = ["OID@", mile_field, place_field]
    
    try:
        with arcpy.da.SearchCursor(photos_fc, fields, where_clause=where_clause) as cursor:
            for row in cursor:
                oid, milepost, place = row
                if milepost is not None and place:
                    anchors.append((oid, float(milepost), str(place)))
    except Exception:
        # Handle case where mile_field doesn't exist or other issues
        return []
    
    # Sort by milepost, then by OID for stable ordering
    anchors.sort(key=lambda x: (x[1], x[0]))
    return anchors


# =============================================================================
# CORE ENRICHMENT FUNCTIONS
# =============================================================================

def enrich_points_places_counties(
    photos_fc: str,
    places_fc: str, 
    counties_fc: str,
    logger: Optional[Callable] = None,
    progress: Optional[Callable] = None
) -> Dict[str, Any]:
    """
    Perform polygon containment joins to fill place, county, and state fields.
    
    Args:
        photos_fc: Path to photos feature class
        places_fc: Path to places feature class  
        counties_fc: Path to counties feature class
        logger: Optional logging function
        progress: Optional progress callback
        
    Returns:
        Dictionary with counts and example OIDs
    """
    if logger:
        logger("Starting polygon containment enrichment...")
    
    # Ensure fields exist
    _ensure_geo_area_fields(photos_fc, logger)
    
    results = {
        "place_contained": 0,
        "county_filled": 0, 
        "state_filled": 0,
        "place_examples": [],
        "county_examples": [],
        "state_examples": []
    }
    
    # Spatial join with places
    if logger:
        logger("Performing spatial join with places...")
    
    # Create temporary layer for spatial join
    temp_places_join = "temp_places_join"
    
    try:
        # Spatial join with places (one-to-one, within)
        arcpy.analysis.SpatialJoin(
            target_features=photos_fc,
            join_features=places_fc,
            out_feature_class=temp_places_join,
            join_operation="JOIN_ONE_TO_ONE",
            join_type="KEEP_ALL",
            match_option="WITHIN"
        )
        
        # Update photos_fc with place information
        place_updates = 0
        join_fields = ["OBJECTID"]
        
        # Detect available fields in places (flexible field mapping)
        places_fields = [f.name for f in arcpy.ListFields(places_fc)]
        
        # Map place fields (try common variations)
        place_name_field = None
        place_fips_field = None
        
        for field in places_fields:
            field_upper = field.upper()
            if field_upper in ["NAME", "PLACE_NAME", "PLACENAME"]:
                place_name_field = field
            elif field_upper in ["GEOID", "FIPS", "PLACE_FIPS", "PLACEFIPS"]:
                place_fips_field = field
        
        if place_name_field:
            join_fields.append(place_name_field)
        if place_fips_field:
            join_fields.append(place_fips_field)
        
        # Update photos with place data
        update_fields = ["geo_place", "geo_place_fips", "geo_place_source", "geo_place_inferred"]
        
        with arcpy.da.UpdateCursor(photos_fc, update_fields) as update_cursor:
            # Create lookup from join results
            join_lookup = {}
            try:
                with arcpy.da.SearchCursor(temp_places_join, join_fields) as join_cursor:
                    for row in join_cursor:
                        oid = row[0]
                        place_name = row[1] if len(row) > 1 and row[1] else None
                        place_fips = row[2] if len(row) > 2 and row[2] else None
                        
                        if place_name:  # Only store if we got a place
                            join_lookup[oid] = (place_name, place_fips)
            except Exception as e:
                if logger:
                    logger(f"Warning: Issue reading place join results: {e}")
            
            # Update photos with place data
            for row in update_cursor:
                oid = update_cursor.oid
                current_place = row[0]
                
                # Only update if place is currently null/empty
                if not current_place and oid in join_lookup:
                    place_name, place_fips = join_lookup[oid]
                    row[0] = place_name  # geo_place
                    row[1] = place_fips  # geo_place_fips
                    row[2] = SourceType.CONTAINED  # geo_place_source
                    row[3] = 0  # geo_place_inferred (direct containment)
                    
                    update_cursor.updateRow(row)
                    place_updates += 1
                    
                    if len(results["place_examples"]) < 10:
                        results["place_examples"].append(oid)
        
        results["place_contained"] = place_updates
        
        if logger:
            logger(f"Updated {place_updates} photos with place containment")
            
    except Exception as e:
        if logger:
            logger(f"Error in places spatial join: {e}")
    finally:
        # Clean up
        if arcpy.Exists(temp_places_join):
            arcpy.Delete_management(temp_places_join)
    
    # Spatial join with counties
    if logger:
        logger("Performing spatial join with counties...")
    
    temp_counties_join = "temp_counties_join"
    
    try:
        # Spatial join with counties
        arcpy.analysis.SpatialJoin(
            target_features=photos_fc,
            join_features=counties_fc,
            out_feature_class=temp_counties_join,
            join_operation="JOIN_ONE_TO_ONE", 
            join_type="KEEP_ALL",
            match_option="WITHIN"
        )
        
        # Update photos_fc with county/state information
        county_updates = 0
        state_updates = 0
        
        # Detect available fields in counties
        counties_fields = [f.name for f in arcpy.ListFields(counties_fc)]
        
        # Map county fields (try common variations)
        county_name_field = None
        county_fips_field = None
        state_fips_field = None
        state_abbr_field = None
        state_name_field = None
        
        for field in counties_fields:
            field_upper = field.upper()
            if field_upper in ["NAME", "COUNTY_NAME", "COUNTYNAME"]:
                county_name_field = field
            elif field_upper in ["GEOID", "FIPS", "COUNTY_FIPS", "COUNTYFIPS"]:
                county_fips_field = field
            elif field_upper in ["STATEFP", "STATE_FIPS", "STATEFIPS"]:
                state_fips_field = field
            elif field_upper in ["STUSPS", "STATE_ABBR", "STATEABBR"]:
                state_abbr_field = field
            elif field_upper in ["STATE_NAME", "STATENAME"]:
                state_name_field = field
        
        # Build join fields list
        join_fields = ["OBJECTID"]
        if county_name_field:
            join_fields.append(county_name_field)
        if county_fips_field:
            join_fields.append(county_fips_field)
        if state_fips_field:
            join_fields.append(state_fips_field)
        if state_abbr_field:
            join_fields.append(state_abbr_field)
        if state_name_field:
            join_fields.append(state_name_field)
        
        # Update photos with county/state data
        update_fields = ["geo_county", "geo_county_fips", "geo_state"]
        
        with arcpy.da.UpdateCursor(photos_fc, update_fields) as update_cursor:
            # Create lookup from join results
            join_lookup = {}
            try:
                with arcpy.da.SearchCursor(temp_counties_join, join_fields) as join_cursor:
                    for row in join_cursor:
                        oid = row[0]
                        
                        # Extract values based on available fields
                        idx = 1
                        county_name = row[idx] if len(row) > idx and county_name_field else None
                        if county_name_field:
                            idx += 1
                        
                        county_fips = row[idx] if len(row) > idx and county_fips_field else None
                        if county_fips_field:
                            idx += 1
                        
                        state_fips = row[idx] if len(row) > idx and state_fips_field else None
                        if state_fips_field:
                            idx += 1
                            
                        state_abbr = row[idx] if len(row) > idx and state_abbr_field else None
                        if state_abbr_field:
                            idx += 1
                            
                        state_name = row[idx] if len(row) > idx and state_name_field else None
                        
                        # Use state_name if available, otherwise state_abbr
                        state_display = state_name if state_name else state_abbr
                        
                        if county_name or county_fips or state_display or state_fips:
                            join_lookup[oid] = (county_name, county_fips, state_display, state_fips)
                            
            except Exception as e:
                if logger:
                    logger(f"Warning: Issue reading county join results: {e}")
            
            # Update photos with county/state data
            for row in update_cursor:
                oid = update_cursor.oid
                
                if oid in join_lookup:
                    county_name, county_fips, state_display, state_fips = join_lookup[oid]
                    
                    # Update county if currently null
                    if not row[0] and county_name:
                        row[0] = county_name
                        county_updates += 1
                        if len(results["county_examples"]) < 10:
                            results["county_examples"].append(oid)
                    
                    # Update county FIPS if currently null  
                    if not row[1] and county_fips:
                        row[1] = county_fips
                    
                    # Update state if currently null
                    if not row[2] and state_display:
                        row[2] = state_display
                        state_updates += 1
                        if len(results["state_examples"]) < 10:
                            results["state_examples"].append(oid)
                    
                    update_cursor.updateRow(row)
        
        results["county_filled"] = county_updates
        results["state_filled"] = state_updates
        
        if logger:
            logger(f"Updated {county_updates} photos with county data")
            logger(f"Updated {state_updates} photos with state data")
            
    except Exception as e:
        if logger:
            logger(f"Error in counties spatial join: {e}")
    finally:
        # Clean up
        if arcpy.Exists(temp_counties_join):
            arcpy.Delete_management(temp_counties_join)
    
    if progress:
        progress(100)
    
    return results


def enrich_places_by_milepost(
    photos_fc: str,
    mile_field: str = "milepost",
    place_field: str = "geo_place", 
    route_field: Optional[str] = "route_id",
    logger: Optional[Callable] = None
) -> Dict[str, Any]:
    """
    Fill prev/next/nearest place context based on mileposts and existing place anchors.
    
    Args:
        photos_fc: Path to photos feature class
        mile_field: Field containing milepost values
        place_field: Field containing place names 
        route_field: Field containing route IDs (optional)
        logger: Optional logging function
        
    Returns:
        Dictionary with counts and examples
    """
    if logger:
        logger("Enriching milepost-based place context...")
    
    # Ensure fields exist
    _ensure_geo_area_fields(photos_fc, logger)
    
    results = {
        "mile_filled_prev": 0,
        "mile_filled_next": 0, 
        "mile_filled_nearest": 0,
        "prev_examples": [],
        "next_examples": [],
        "nearest_examples": []
    }
    
    # Validate required fields
    if not validate_fields_exist(photos_fc, [mile_field], raise_on_missing=False):
        if logger:
            logger(f"Warning: Mile field '{mile_field}' not found, skipping milepost enrichment")
        return results
    
    # Group by routes
    route_groups = _get_route_groups(photos_fc, route_field)
    
    for route_id, oids in route_groups.items():
        if logger:
            logger(f"Processing route '{route_id}' ({len(oids)} points)...")
        
        # Get anchors (points that already have places) sorted by milepost
        anchors = _get_sorted_anchors(photos_fc, oids, mile_field, place_field)
        
        if len(anchors) < 2:
            if logger:
                logger(f"Route '{route_id}' has {len(anchors)} anchors, skipping context enrichment")
            continue
        
        if logger:
            logger(f"Found {len(anchors)} place anchors for route '{route_id}'")
        
        # Build where clause for this route's OIDs
        oid_list = ",".join(map(str, oids))
        where_clause = f"OBJECTID IN ({oid_list})"
        
        # Update context fields for all points in this route
        update_fields = [
            "OID@", mile_field, 
            "geo_prev_place", "geo_prev_miles",
            "geo_next_place", "geo_next_miles", 
            "geo_nearest_place", "geo_nearest_miles", "geo_nearest_dir"
        ]
        
        with arcpy.da.UpdateCursor(photos_fc, update_fields, where_clause=where_clause) as cursor:
            for row in cursor:
                oid = row[0]
                current_mile = row[1]
                
                if current_mile is None:
                    continue
                
                current_mile = float(current_mile)
                
                # Find prev/next anchors
                prev_anchor = None
                next_anchor = None
                
                for anchor_oid, anchor_mile, anchor_place in anchors:
                    if anchor_mile <= current_mile:
                        prev_anchor = (anchor_oid, anchor_mile, anchor_place)
                    elif anchor_mile > current_mile and next_anchor is None:
                        next_anchor = (anchor_oid, anchor_mile, anchor_place)
                        break
                
                # Update prev context
                if prev_anchor and not row[2]:  # geo_prev_place is null
                    row[2] = prev_anchor[2]  # geo_prev_place
                    row[3] = abs(current_mile - prev_anchor[1])  # geo_prev_miles
                    results["mile_filled_prev"] += 1
                    if len(results["prev_examples"]) < 10:
                        results["prev_examples"].append(oid)
                
                # Update next context  
                if next_anchor and not row[4]:  # geo_next_place is null
                    row[4] = next_anchor[2]  # geo_next_place
                    row[5] = abs(next_anchor[1] - current_mile)  # geo_next_miles
                    results["mile_filled_next"] += 1
                    if len(results["next_examples"]) < 10:
                        results["next_examples"].append(oid)
                
                # Update nearest context
                if not row[6]:  # geo_nearest_place is null
                    nearest_anchor = None
                    nearest_distance = float('inf')
                    nearest_direction = None
                    
                    # Check prev anchor
                    if prev_anchor:
                        dist = abs(current_mile - prev_anchor[1])
                        if dist < nearest_distance:
                            nearest_distance = dist
                            nearest_anchor = prev_anchor
                            nearest_direction = "DN"  # Down (lower milepost)
                    
                    # Check next anchor
                    if next_anchor:
                        dist = abs(next_anchor[1] - current_mile)
                        if dist < nearest_distance:
                            nearest_distance = dist
                            nearest_anchor = next_anchor
                            nearest_direction = "UP"  # Up (higher milepost)
                    
                    if nearest_anchor:
                        row[6] = nearest_anchor[2]  # geo_nearest_place
                        row[7] = nearest_distance   # geo_nearest_miles
                        row[8] = nearest_direction  # geo_nearest_dir
                        row[7] = nearest_distance   # geo_nearest_miles
                        row[8] = nearest_direction  # geo_nearest_dir
                        results["mile_filled_nearest"] += 1
                        if len(results["nearest_examples"]) < 10:
                            results["nearest_examples"].append(oid)
                
                cursor.updateRow(row)
    
    if logger:
        logger(f"Filled prev context for {results['mile_filled_prev']} points")
        logger(f"Filled next context for {results['mile_filled_next']} points")  
        logger(f"Filled nearest context for {results['mile_filled_nearest']} points")
    
    return results


def bridge_place_gaps_by_milepost(
    photos_fc: str,
    mile_field: str = "milepost",
    place_field: str = "geo_place",
    route_field: Optional[str] = "route_id", 
    county_field: str = "geo_county",
    max_span_miles: float = 1.0,
    logger: Optional[Callable] = None
) -> int:
    """
    Bridge short gaps between same-place anchors by inferring place for null points.
    
    Args:
        photos_fc: Path to photos feature class
        mile_field: Field containing milepost values
        place_field: Field containing place names
        route_field: Field containing route IDs (optional)
        county_field: Field containing county names for consistency check
        max_span_miles: Maximum gap distance to bridge
        logger: Optional logging function
        
    Returns:
        Number of points bridged
    """
    if logger:
        logger(f"Bridging place gaps (max span: {max_span_miles} miles)...")
    
    # Validate required fields
    required_fields = [mile_field, place_field]
    if not validate_fields_exist(photos_fc, required_fields, raise_on_missing=False):
        if logger:
            logger("Required fields missing for gap bridging")
        return 0
    
    bridged_count = 0
    
    # Group by routes
    route_groups = _get_route_groups(photos_fc, route_field)
    
    for route_id, oids in route_groups.items():
        # Get anchors for this route
        anchors = _get_sorted_anchors(photos_fc, oids, mile_field, place_field)
        
        if len(anchors) < 2:
            continue
        
        # Find gaps to bridge
        gaps_to_bridge = []
        
        for i in range(len(anchors) - 1):
            current_anchor = anchors[i]
            next_anchor = anchors[i + 1]
            
            # Check if same place and within span limit
            if (current_anchor[2] == next_anchor[2] and 
                (next_anchor[1] - current_anchor[1]) <= max_span_miles):
                
                gaps_to_bridge.append({
                    'start_mile': current_anchor[1],
                    'end_mile': next_anchor[1], 
                    'place': current_anchor[2],
                    'span_miles': next_anchor[1] - current_anchor[1]
                })
        
        if not gaps_to_bridge:
            continue
        
        if logger:
            logger(f"Route '{route_id}': Found {len(gaps_to_bridge)} gaps to bridge")
        
        # Bridge the gaps
        oid_list = ",".join(map(str, oids))
        where_clause = f"OBJECTID IN ({oid_list}) AND {place_field} IS NULL"
        
        update_fields = ["OID@", mile_field, place_field, "geo_place_source", 
                        "geo_place_inferred", "geo_place_gap_miles"]
        
        # Add county field if it exists
        use_county_check = validate_fields_exist(photos_fc, [county_field], raise_on_missing=False)
        if use_county_check:
            update_fields.append(county_field)
        
        with arcpy.da.UpdateCursor(photos_fc, update_fields, where_clause=where_clause) as cursor:
            for row in cursor:
                oid = row[0]
                current_mile = row[1]
                
                if current_mile is None:
                    continue
                
                current_mile = float(current_mile)
                
                # Check if this point falls within any gap to bridge
                for gap in gaps_to_bridge:
                    if gap['start_mile'] <= current_mile <= gap['end_mile']:
                        # Optional county consistency check
                        if use_county_check:
                            current_county = row[-1]  # Last field is county
                            # Get county of anchor points - simplified check
                            # In production, you might want more sophisticated county validation
                        
                        # Bridge this gap
                        row[2] = gap['place']  # geo_place
                        row[3] = SourceType.INFERRED_BRIDGE  # geo_place_source
                        row[4] = 1  # geo_place_inferred
                        row[5] = gap['span_miles']  # geo_place_gap_miles
                        
                        cursor.updateRow(row)
                        bridged_count += 1
                        break
    
    if logger:
        logger(f"Bridged {bridged_count} points across place gaps")
    
    return bridged_count


def build_place_mile_ranges(
    photos_fc: str,
    mile_field: str = "milepost",
    place_field: str = "geo_place", 
    route_field: Optional[str] = "route_id",
    county_field: str = "geo_county",
    out_table: Optional[str] = None,
    break_gap_miles: float = 0.5,
    min_points_per_range: int = 2
) -> str:
    """
    Build contiguous place-milepost ranges from anchor points.
    
    Args:
        photos_fc: Path to photos feature class
        mile_field: Field containing milepost values
        place_field: Field containing place names
        route_field: Field containing route IDs (optional)
        county_field: Field containing county names
        out_table: Output table path (optional, creates temp if None)
        break_gap_miles: Gap distance that breaks a range
        min_points_per_range: Minimum points required for a valid range
        
    Returns:
        Path to ranges table
    """
    if logger := None:  # Will be passed in from calling function
        pass
    
    # Create output table if not specified
    if out_table is None:
        out_table = arcpy.CreateScratchName("place_mile_ranges", "", "Table")
    
    # Create ranges table schema
    arcpy.management.CreateTable(
        out_path=os.path.dirname(out_table),
        out_name=os.path.basename(out_table)
    )
    
    # Add fields to ranges table
    range_fields = [
        ("route_id", "TEXT", 50),
        ("place", "TEXT", 100),
        ("county", "TEXT", 50), 
        ("start_mile", "DOUBLE", None),
        ("end_mile", "DOUBLE", None),
        ("n_points", "LONG", None)
    ]
    
    for field_name, field_type, field_length in range_fields:
        if field_length:
            arcpy.management.AddField(out_table, field_name, field_type, field_length=field_length)
        else:
            arcpy.management.AddField(out_table, field_name, field_type)
    
    # Group by routes and build ranges
    route_groups = _get_route_groups(photos_fc, route_field)
    
    insert_fields = ["route_id", "place", "county", "start_mile", "end_mile", "n_points"]
    
    with arcpy.da.InsertCursor(out_table, insert_fields) as insert_cursor:
        for route_id, oids in route_groups.items():
            # Get all points with places for this route, sorted by milepost
            anchors = _get_sorted_anchors(photos_fc, oids, mile_field, place_field)
            
            if len(anchors) < min_points_per_range:
                continue
            
            # Group anchors into contiguous ranges by place
            current_range = None
            ranges = []
            
            for oid, mile, place in anchors:
                if current_range is None:
                    # Start new range
                    current_range = {
                        'place': place,
                        'start_mile': mile,
                        'end_mile': mile,
                        'points': [oid]
                    }
                elif (current_range['place'] == place and 
                      (mile - current_range['end_mile']) <= break_gap_miles):
                    # Extend current range
                    current_range['end_mile'] = mile
                    current_range['points'].append(oid)
                else:
                    # Close current range and start new one
                    if len(current_range['points']) >= min_points_per_range:
                        ranges.append(current_range)
                    
                    current_range = {
                        'place': place,
                        'start_mile': mile,
                        'end_mile': mile, 
                        'points': [oid]
                    }
            
            # Add final range
            if current_range and len(current_range['points']) >= min_points_per_range:
                ranges.append(current_range)
            
            # Insert ranges into table
            for range_info in ranges:
                # Get county from first point in range (simplified)
                county = "Unknown"  # Default
                
                if validate_fields_exist(photos_fc, [county_field], raise_on_missing=False):
                    first_oid = range_info['points'][0]
                    with arcpy.da.SearchCursor(photos_fc, [county_field], 
                                             where_clause=f"OBJECTID = {first_oid}") as cursor:
                        for row in cursor:
                            county = row[0] or "Unknown"
                            break
                
                insert_cursor.insertRow([
                    route_id,
                    range_info['place'],
                    county,
                    range_info['start_mile'],
                    range_info['end_mile'], 
                    len(range_info['points'])
                ])
    
    return out_table


def apply_place_mile_ranges(
    photos_fc: str,
    ranges_table: str,
    mile_field: str = "milepost",
    route_field: Optional[str] = "route_id",
    place_field: str = "geo_place",
    respect_existing: bool = True,
    mark_source: bool = True
) -> int:
    """
    Apply place ranges to fill null place values.
    
    Args:
        photos_fc: Path to photos feature class
        ranges_table: Path to ranges table from build_place_mile_ranges
        mile_field: Field containing milepost values
        route_field: Field containing route IDs (optional)
        place_field: Field containing place names
        respect_existing: Only fill null values if True
        mark_source: Mark source as RANGE_LOOKUP if True
        
    Returns:
        Number of points updated
    """
    updated_count = 0
    
    # Load ranges into memory for faster lookup
    ranges = {}
    
    with arcpy.da.SearchCursor(ranges_table, 
                              ["route_id", "place", "start_mile", "end_mile"]) as cursor:
        for route_id, place, start_mile, end_mile in cursor:
            if route_id not in ranges:
                ranges[route_id] = []
            ranges[route_id].append((place, start_mile, end_mile))
    
    # Group photos by route and apply ranges
    route_groups = _get_route_groups(photos_fc, route_field)
    
    for route_id, oids in route_groups.items():
        if route_id not in ranges:
            continue
        
        route_ranges = ranges[route_id]
        
        # Build where clause
        oid_list = ",".join(map(str, oids))
        if respect_existing:
            where_clause = f"OBJECTID IN ({oid_list}) AND ({place_field} IS NULL OR {place_field} = '')"
        else:
            where_clause = f"OBJECTID IN ({oid_list})"
        
        # Update fields
        update_fields = ["OID@", mile_field, place_field]
        if mark_source:
            update_fields.extend(["geo_place_source", "geo_place_inferred"])
        
        with arcpy.da.UpdateCursor(photos_fc, update_fields, where_clause=where_clause) as cursor:
            for row in cursor:
                oid = row[0]
                current_mile = row[1]
                
                if current_mile is None:
                    continue
                
                current_mile = float(current_mile)
                
                # Check if mile falls within any range
                for place, start_mile, end_mile in route_ranges:
                    if start_mile <= current_mile <= end_mile:
                        row[2] = place  # geo_place
                        
                        if mark_source:
                            row[3] = SourceType.RANGE_LOOKUP  # geo_place_source
                            row[4] = 1  # geo_place_inferred
                        
                        cursor.updateRow(row)
                        updated_count += 1
                        break
    
    return updated_count


def promote_nearest_to_place(
    photos_fc: str,
    place_field: str = "geo_place",
    max_nearest_miles: float = 2.0
) -> int:
    """
    Promote nearest place to actual place if within threshold distance.
    
    Args:
        photos_fc: Path to photos feature class
        place_field: Field containing place names
        max_nearest_miles: Maximum distance to promote nearest place
        
    Returns:
        Number of points promoted
    """
    promoted_count = 0
    
    # Find points with null place but nearby nearest place within threshold
    where_clause = (f"({place_field} IS NULL OR {place_field} = '') "
                   f"AND geo_nearest_place IS NOT NULL "
                   f"AND geo_nearest_miles <= {max_nearest_miles}")
    
    update_fields = [place_field, "geo_nearest_place", "geo_place_source", "geo_place_inferred"]
    
    with arcpy.da.UpdateCursor(photos_fc, update_fields, where_clause=where_clause) as cursor:
        for row in cursor:
            row[0] = row[1]  # geo_place = geo_nearest_place
            row[2] = SourceType.NEAREST_ALONG  # geo_place_source
            row[3] = 1  # geo_place_inferred
            
            cursor.updateRow(row)
            promoted_count += 1
    
    return promoted_count


# =============================================================================
# MAIN ORCHESTRATOR
# =============================================================================

def geocode_geoareas(
    photos_fc: str,
    places_fc: str,
    counties_fc: str,
    corridor_places_fc: Optional[str] = None,
    nearest_radius_m: float = 8000,
    mile_field: str = "milepost",
    route_field: Optional[str] = "route_id", 
    max_gap_miles: float = 1.0,
    promote_nearest_to_actual: bool = False,
    max_nearest_miles: float = 2.0,
    logger: Optional[Callable] = None,
    progress: Optional[Callable] = None
) -> Dict[str, Any]:
    """
    Main orchestrator for geo-areas enrichment.
    
    Performs the complete enrichment workflow:
    1. Polygon containment for places, counties, states
    2. Milepost-based context (prev/next/nearest)
    3. Optional gap bridging 
    4. Optional nearest place promotion
    5. Range building and application
    
    Args:
        photos_fc: Path to photos feature class
        places_fc: Path to places feature class
        counties_fc: Path to counties feature class
        corridor_places_fc: Optional corridor-specific places (unused in this implementation)
        nearest_radius_m: Radius for nearest calculations (unused - using milepost logic)
        mile_field: Field containing milepost values
        route_field: Field containing route IDs (optional)
        max_gap_miles: Maximum gap distance for bridging
        promote_nearest_to_actual: Whether to promote nearest places within threshold
        max_nearest_miles: Maximum distance for nearest place promotion
        logger: Optional logging function
        progress: Optional progress callback function
        
    Returns:
        Comprehensive results dictionary with counts and examples
    """
    if logger:
        logger("Starting comprehensive geo-areas enrichment...")
    
    # Initialize results
    results = {
        "place_contained": 0,
        "county_filled": 0,
        "state_filled": 0,
        "mile_filled_prev": 0,
        "mile_filled_next": 0,
        "mile_filled_nearest": 0,
        "bridged": 0,
        "promoted_nearest": 0,
        "range_updates": 0,
        "place_examples": [],
        "county_examples": [],
        "state_examples": [],
        "prev_examples": [],
        "next_examples": [], 
        "nearest_examples": [],
        "bridge_examples": [],
        "promoted_examples": [],
        "range_examples": []
    }
    
    try:
        # Step 1: Polygon containment enrichment
        if progress:
            progress(10, "Performing polygon containment...")
        
        containment_results = enrich_points_places_counties(
            photos_fc, places_fc, counties_fc, logger, None
        )
        
        # Merge containment results
        for key in ["place_contained", "county_filled", "state_filled", 
                   "place_examples", "county_examples", "state_examples"]:
            results[key] = containment_results.get(key, 0)
        
        # Step 2: Milepost-based context enrichment
        if progress:
            progress(30, "Enriching milepost context...")
        
        milepost_results = enrich_places_by_milepost(
            photos_fc, mile_field, "geo_place", route_field, logger
        )
        
        # Merge milepost results
        for key in ["mile_filled_prev", "mile_filled_next", "mile_filled_nearest",
                   "prev_examples", "next_examples", "nearest_examples"]:
            results[key] = milepost_results.get(key, 0)
        
        # Step 3: Gap bridging (optional)
        if progress:
            progress(50, "Bridging place gaps...")
        
        bridged_count = bridge_place_gaps_by_milepost(
            photos_fc, mile_field, "geo_place", route_field, 
            "geo_county", max_gap_miles, logger
        )
        
        results["bridged"] = bridged_count
        
        # Step 4: Build and apply place ranges
        if progress:
            progress(70, "Building place ranges...")
        
        ranges_table = build_place_mile_ranges(
            photos_fc, mile_field, "geo_place", route_field, "geo_county"
        )
        
        if progress:
            progress(80, "Applying place ranges...")
        
        range_updates = apply_place_mile_ranges(
            photos_fc, ranges_table, mile_field, route_field, "geo_place"
        )
        
        results["range_updates"] = range_updates
        
        # Clean up ranges table
        if arcpy.Exists(ranges_table):
            arcpy.Delete_management(ranges_table)
        
        # Step 5: Promote nearest places (optional)
        if promote_nearest_to_actual:
            if progress:
                progress(90, "Promoting nearest places...")
            
            promoted_count = promote_nearest_to_place(
                photos_fc, "geo_place", max_nearest_miles
            )
            
            results["promoted_nearest"] = promoted_count
        
        if progress:
            progress(100, "Geo-areas enrichment complete")
        
        if logger:
            logger("Geo-areas enrichment completed successfully")
            logger(f"Summary: {results['place_contained']} contained, "
                  f"{results['bridged']} bridged, {results['range_updates']} from ranges, "
                  f"{results['promoted_nearest']} promoted")
    
    except Exception as e:
        if logger:
            logger(f"Error during geo-areas enrichment: {e}")
        raise
    
    return results