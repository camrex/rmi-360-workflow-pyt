# =============================================================================
# 🌍 Geocode Geo-Areas Unit Tests (tests/test_geocode_geoareas.py)
# -----------------------------------------------------------------------------
# Purpose:             Unit tests for the geo-areas enrichment utility
# Project:             RMI 360 Imaging Workflow Python Toolbox  
# Version:             1.0.0
# Author:              RMI Valuation, LLC
# Created:             2025-11-02
#
# Description:
#   Unit tests for the geocode_geoareas utility functions. Uses in-memory
#   feature classes where possible to avoid file system dependencies.
#
# File Location:        /tests/test_geocode_geoareas.py
# Test Target:          utils/geocode_geoareas.py
# Dependencies:         arcpy, unittest
# =============================================================================

import unittest
import arcpy
import os
import tempfile
from pathlib import Path

from utils.geocode_geoareas import (
    _ensure_geo_area_fields, _get_route_groups, _get_sorted_anchors,
    enrich_points_places_counties, enrich_places_by_milepost,
    bridge_place_gaps_by_milepost, GEO_AREA_FIELDS, SourceType
)
from utils.validators.geocode_geoareas_validator import validate_geocode_geoareas_inputs


class TestGeocodeGeoAreas(unittest.TestCase):
    """Test cases for geo-areas enrichment utilities."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
        # Create temporary workspace
        cls.temp_dir = tempfile.mkdtemp()
        cls.test_gdb = os.path.join(cls.temp_dir, "test_geocode.gdb")
        arcpy.management.CreateFileGDB(cls.temp_dir, "test_geocode.gdb")
        
        # Test feature class names
        cls.photos_fc = os.path.join(cls.test_gdb, "test_photos")
        cls.places_fc = os.path.join(cls.test_gdb, "test_places") 
        cls.counties_fc = os.path.join(cls.test_gdb, "test_counties")
        
    @classmethod
    def tearDownClass(cls):
        """Clean up test environment."""
        try:
            if arcpy.Exists(cls.test_gdb):
                arcpy.Delete_management(cls.test_gdb)
            if os.path.exists(cls.temp_dir):
                import shutil
                shutil.rmtree(cls.temp_dir, ignore_errors=True)
        except:
            pass
    
    def setUp(self):
        """Set up each test."""
        # Clean up any existing test data
        for fc in [self.photos_fc, self.places_fc, self.counties_fc]:
            if arcpy.Exists(fc):
                arcpy.Delete_management(fc)
    
    def _create_test_photos_fc(self, with_routes=False):
        """Create test photos feature class with sample data."""
        # Create point feature class
        sr = arcpy.SpatialReference(4326)  # WGS84
        arcpy.management.CreateFeatureclass(
            self.test_gdb, "test_photos", "POINT", spatial_reference=sr
        )
        
        # Add fields
        arcpy.management.AddField(self.photos_fc, "milepost", "DOUBLE")
        if with_routes:
            arcpy.management.AddField(self.photos_fc, "route_id", "TEXT", field_length=20)
        
        # Insert test data
        fields = ["SHAPE@", "milepost"]
        if with_routes:
            fields.append("route_id")
        
        with arcpy.da.InsertCursor(self.photos_fc, fields) as cursor:
            test_points = [
                # Route A points
                (arcpy.Point(-84.0, 39.0), 0.0, "Route_A"),
                (arcpy.Point(-84.0, 39.1), 0.5, "Route_A"), 
                (arcpy.Point(-84.0, 39.2), 1.0, "Route_A"),
                (arcpy.Point(-84.0, 39.3), 1.5, "Route_A"),
                (arcpy.Point(-84.0, 39.4), 2.0, "Route_A"),
                # Route B points  
                (arcpy.Point(-85.0, 40.0), 0.0, "Route_B"),
                (arcpy.Point(-85.0, 40.1), 0.5, "Route_B"),
                (arcpy.Point(-85.0, 40.2), 1.0, "Route_B"),
            ]
            
            for point_data in test_points:
                if with_routes:
                    cursor.insertRow(point_data)
                else:
                    cursor.insertRow(point_data[:2])  # Just point and milepost
    
    def _create_test_places_fc(self):
        """Create test places feature class with sample data."""
        # Create polygon feature class
        sr = arcpy.SpatialReference(4326)  # WGS84
        arcpy.management.CreateFeatureclass(
            self.test_gdb, "test_places", "POLYGON", spatial_reference=sr
        )
        
        # Add fields
        arcpy.management.AddField(self.places_fc, "NAME", "TEXT", field_length=50)
        arcpy.management.AddField(self.places_fc, "GEOID", "TEXT", field_length=20)
        
        # Create simple rectangular polygons around test points
        with arcpy.da.InsertCursor(self.places_fc, ["SHAPE@", "NAME", "GEOID"]) as cursor:
            # Place around first few points
            poly1 = arcpy.Polygon(arcpy.Array([
                arcpy.Point(-84.1, 38.9),
                arcpy.Point(-83.9, 38.9), 
                arcpy.Point(-83.9, 39.2),
                arcpy.Point(-84.1, 39.2)
            ]), sr)
            cursor.insertRow([poly1, "Test City A", "12345"])
            
            # Place around Route B points
            poly2 = arcpy.Polygon(arcpy.Array([
                arcpy.Point(-85.1, 39.9),
                arcpy.Point(-84.9, 39.9),
                arcpy.Point(-84.9, 40.2), 
                arcpy.Point(-85.1, 40.2)
            ]), sr)
            cursor.insertRow([poly2, "Test City B", "67890"])
    
    def _create_test_counties_fc(self):
        """Create test counties feature class with sample data."""
        # Create polygon feature class
        sr = arcpy.SpatialReference(4326)  # WGS84
        arcpy.management.CreateFeatureclass(
            self.test_gdb, "test_counties", "POLYGON", spatial_reference=sr
        )
        
        # Add fields
        arcpy.management.AddField(self.counties_fc, "NAME", "TEXT", field_length=50)
        arcpy.management.AddField(self.counties_fc, "GEOID", "TEXT", field_length=10) 
        arcpy.management.AddField(self.counties_fc, "STATEFP", "TEXT", field_length=2)
        arcpy.management.AddField(self.counties_fc, "STUSPS", "TEXT", field_length=2)
        
        # Create large county polygon covering all test points
        with arcpy.da.InsertCursor(self.counties_fc, 
                                  ["SHAPE@", "NAME", "GEOID", "STATEFP", "STUSPS"]) as cursor:
            county_poly = arcpy.Polygon(arcpy.Array([
                arcpy.Point(-86.0, 38.5),
                arcpy.Point(-83.0, 38.5),
                arcpy.Point(-83.0, 41.0),
                arcpy.Point(-86.0, 41.0)
            ]), sr)
            cursor.insertRow([county_poly, "Test County", "12001", "12", "OH"])
    
    def test_ensure_geo_area_fields(self):
        """Test field creation functionality."""
        self._create_test_photos_fc()
        
        # Verify initial state - should not have geo-area fields
        initial_fields = [f.name for f in arcpy.ListFields(self.photos_fc)]
        self.assertNotIn("geo_place", initial_fields)
        
        # Add geo-area fields
        _ensure_geo_area_fields(self.photos_fc)
        
        # Verify fields were added
        final_fields = [f.name for f in arcpy.ListFields(self.photos_fc)]
        expected_fields = [field_name for field_name, _, _ in GEO_AREA_FIELDS]
        
        for field_name in expected_fields:
            self.assertIn(field_name, final_fields)
    
    def test_get_route_groups(self):
        """Test route grouping functionality."""
        # Test with routes
        self._create_test_photos_fc(with_routes=True)
        
        route_groups = _get_route_groups(self.photos_fc, "route_id")
        
        self.assertIn("Route_A", route_groups)
        self.assertIn("Route_B", route_groups)
        self.assertEqual(len(route_groups["Route_A"]), 5)
        self.assertEqual(len(route_groups["Route_B"]), 3)
        
        # Test without routes (should create default group)
        route_groups_no_field = _get_route_groups(self.photos_fc, None)
        self.assertIn("default_route", route_groups_no_field)
        self.assertEqual(len(route_groups_no_field["default_route"]), 8)
    
    def test_validator_basic(self):
        """Test basic input validation."""
        # Test with non-existent files
        is_valid, errors = validate_geocode_geoareas_inputs(
            "nonexistent_photos", "nonexistent_places", "nonexistent_counties"
        )
        
        self.assertFalse(is_valid)
        self.assertTrue(len(errors) >= 3)  # Should have at least 3 existence errors
        
        # Test with valid files
        self._create_test_photos_fc()
        self._create_test_places_fc()
        self._create_test_counties_fc()
        
        is_valid, errors = validate_geocode_geoareas_inputs(
            self.photos_fc, self.places_fc, self.counties_fc
        )
        
        # Should be valid with our test data
        if not is_valid:
            print(f"Validation errors: {errors}")
        self.assertTrue(is_valid)
    
    def test_containment_enrichment(self):
        """Test polygon containment enrichment."""
        self._create_test_photos_fc()
        self._create_test_places_fc() 
        self._create_test_counties_fc()
        
        # Run containment enrichment
        results = enrich_points_places_counties(
            self.photos_fc, self.places_fc, self.counties_fc
        )
        
        # Verify results structure
        self.assertIn("place_contained", results)
        self.assertIn("county_filled", results)
        self.assertIn("state_filled", results)
        
        # Should have enriched some points (at least those in places)
        self.assertGreater(results["place_contained"], 0)
        self.assertGreater(results["county_filled"], 0)
        
        # Verify data was actually written
        place_count = 0
        with arcpy.da.SearchCursor(self.photos_fc, ["geo_place", "geo_county", "geo_state"]) as cursor:
            for row in cursor:
                if row[0]:  # geo_place
                    place_count += 1
                # All should have county/state since our county covers everything
                self.assertIsNotNone(row[1])  # geo_county
                self.assertIsNotNone(row[2])  # geo_state
        
        self.assertEqual(place_count, results["place_contained"])
    
    def test_milepost_enrichment(self):
        """Test milepost-based context enrichment.""" 
        self._create_test_photos_fc(with_routes=True)
        self._ensure_geo_area_fields(self.photos_fc)
        
        # Add some place anchors manually
        with arcpy.da.UpdateCursor(self.photos_fc, 
                                  ["OID@", "milepost", "geo_place", "route_id"]) as cursor:
            for row in cursor:
                oid, mile, place, route = row
                # Set places for first and last point in each route
                if (route == "Route_A" and mile in [0.0, 2.0]) or \
                   (route == "Route_B" and mile in [0.0, 1.0]):
                    row[2] = f"Anchor_{route}_{mile}"
                    cursor.updateRow(row)
        
        # Run milepost enrichment
        results = enrich_places_by_milepost(
            self.photos_fc, "milepost", "geo_place", "route_id"
        )
        
        # Verify results
        self.assertIn("mile_filled_prev", results)
        self.assertIn("mile_filled_next", results)
        self.assertIn("mile_filled_nearest", results)
        
        # Should have filled context for points between anchors
        self.assertGreater(results["mile_filled_prev"], 0)
        self.assertGreater(results["mile_filled_next"], 0)
        self.assertGreater(results["mile_filled_nearest"], 0)
    
    def test_gap_bridging(self):
        """Test gap bridging functionality."""
        self._create_test_photos_fc()
        _ensure_geo_area_fields(self.photos_fc)
        
        # Set up scenario: same place at miles 0.0 and 2.0, gap in between
        with arcpy.da.UpdateCursor(self.photos_fc, 
                                  ["milepost", "geo_place"]) as cursor:
            for row in cursor:
                mile = row[0]
                if mile in [0.0, 2.0]:
                    row[1] = "Same Place"
                    cursor.updateRow(row)
        
        # Run gap bridging (max gap 2.5 miles should bridge this)
        bridged_count = bridge_place_gaps_by_milepost(
            self.photos_fc, "milepost", "geo_place", 
            max_span_miles=2.5
        )
        
        # Should have bridged the intermediate points
        self.assertGreater(bridged_count, 0)
        
        # Verify bridged points have correct source marking
        with arcpy.da.SearchCursor(self.photos_fc, 
                                  ["milepost", "geo_place", "geo_place_source"]) as cursor:
            bridged_found = False
            for row in cursor:
                mile, place, source = row
                if place == "Same Place" and mile not in [0.0, 2.0]:
                    self.assertEqual(source, SourceType.INFERRED_BRIDGE)
                    bridged_found = True
            
            self.assertTrue(bridged_found, "Should have found at least one bridged point")


class TestGeocodeGeoAreasIntegration(unittest.TestCase):
    """Integration tests for the complete geo-areas workflow."""
    
    def setUp(self):
        """Set up integration test environment.""" 
        # These would typically use real test data files
        # For now, just verify the functions can be imported and called
        pass
    
    def test_full_workflow_import(self):
        """Test that all workflow functions can be imported."""
        from utils.geocode_geoareas import geocode_geoareas
        
        # Verify the main orchestrator function exists and is callable
        self.assertTrue(callable(geocode_geoareas))
    
    def test_tool_import(self):
        """Test that the ArcGIS tool can be imported."""
        from tools.geocode_geoareas_tool import GeocodeGeoAreasTool
        
        # Verify tool class exists
        tool = GeocodeGeoAreasTool()
        self.assertEqual(tool.label, "08 - Geocode Geo-Areas")
        self.assertTrue(tool.canRunInBackground)
        
        # Verify parameter structure
        params = tool.getParameterInfo()
        self.assertGreater(len(params), 10)  # Should have multiple parameters
        
        # Check key parameters exist
        param_names = [p.name for p in params]
        expected_params = ["photos_fc", "places_fc", "counties_fc", "mode"]
        for expected in expected_params:
            self.assertIn(expected, param_names)


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)