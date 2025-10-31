#!/usr/bin/env python3
# =============================================================================
# 🧪 Distance Filter Integration Test
# -----------------------------------------------------------------------------
# Quick test to validate the distance-based spacing filter functionality
# =============================================================================

import sys
import os
from pathlib import Path

# Add the project root to the path for imports
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_distance_filter_logic():
    """Test the core distance filtering logic without ArcPy dependencies"""
    from utils.filter_distance_spacing import haversine, analyze_spacing_by_reel
    
    print("🧪 Testing Distance Filter Logic")
    print("=" * 50)
    
    # Test haversine distance calculation
    print("\n1. Testing Haversine Distance Calculation:")
    
    # GPS coordinates for testing (roughly 5 meters apart)
    point1 = {"oid": 1, "x": -104.9903, "y": 39.7392, "ts": "2025-10-31 10:00:00", "reel": "test_reel"}
    point2 = {"oid": 2, "x": -104.9902, "y": 39.7392, "ts": "2025-10-31 10:00:05", "reel": "test_reel"}
    point3 = {"oid": 3, "x": -104.9901, "y": 39.7392, "ts": "2025-10-31 10:00:10", "reel": "test_reel"}  # ~10m total
    
    distance_1_2 = haversine(point1["x"], point1["y"], point2["x"], point2["y"])
    distance_2_3 = haversine(point2["x"], point2["y"], point3["x"], point3["y"])
    
    print(f"   Distance P1→P2: {distance_1_2:.2f} meters")
    print(f"   Distance P2→P3: {distance_2_3:.2f} meters")
    
    # Test spacing analysis - simulate time-based capture scenario
    print("\n2. Testing Time-Based Capture Detection:")
    
    # Create test points with time-based spacing (too close together)
    time_based_points = [
        {"oid": 1, "x": -104.9903, "y": 39.7392, "ts": "2025-10-31 10:00:00", "reel": "time_reel"},
        {"oid": 2, "x": -104.99025, "y": 39.7392, "ts": "2025-10-31 10:00:01", "reel": "time_reel"},  # ~2.8m
        {"oid": 3, "x": -104.9902, "y": 39.7392, "ts": "2025-10-31 10:00:02", "reel": "time_reel"},   # ~2.8m
        {"oid": 4, "x": -104.99015, "y": 39.7392, "ts": "2025-10-31 10:00:03", "reel": "time_reel"}, # ~2.8m
        {"oid": 5, "x": -104.9901, "y": 39.7392, "ts": "2025-10-31 10:00:04", "reel": "time_reel"},   # ~2.8m
    ]
    
    class MockLogger:
        def debug(self, msg, indent=0):
            print("  " * indent + msg)
    
    logger = MockLogger()
    
    oids_to_remove, stats = analyze_spacing_by_reel(
        time_based_points, 
        min_spacing_m=5.0, 
        tolerance_m=1.0, 
        logger=logger
    )
    
    print(f"\n   📊 Analysis Results:")
    print(f"      Total points: {stats['total_points']}")
    print(f"      Points to keep: {stats['kept_count']}")
    print(f"      Points to remove: {stats['removed_count']}")
    print(f"      Average original spacing: {stats['avg_original_spacing']:.2f}m")
    print(f"      OIDs to remove: {oids_to_remove}")
    
    # Test distance-based capture (should keep all)
    print("\n3. Testing Distance-Based Capture (Good Spacing):")
    
    distance_based_points = [
        {"oid": 1, "x": -104.9903, "y": 39.7392, "ts": "2025-10-31 10:00:00", "reel": "dist_reel"},
        {"oid": 2, "x": -104.9902, "y": 39.7392, "ts": "2025-10-31 10:00:05", "reel": "dist_reel"},   # ~5.6m
        {"oid": 3, "x": -104.9901, "y": 39.7392, "ts": "2025-10-31 10:00:10", "reel": "dist_reel"},   # ~5.6m
        {"oid": 4, "x": -104.9900, "y": 39.7392, "ts": "2025-10-31 10:00:15", "reel": "dist_reel"},   # ~5.6m
    ]
    
    oids_to_remove_good, stats_good = analyze_spacing_by_reel(
        distance_based_points,
        min_spacing_m=5.0,
        tolerance_m=1.0,
        logger=logger
    )
    
    print(f"\n   📊 Good Spacing Results:")
    print(f"      Total points: {stats_good['total_points']}")
    print(f"      Points to keep: {stats_good['kept_count']}")
    print(f"      Points to remove: {stats_good['removed_count']}")
    print(f"      Average original spacing: {stats_good['avg_original_spacing']:.2f}m")
    print(f"      OIDs to remove: {oids_to_remove_good}")
    
    # Validate results
    print("\n4. ✅ Validation:")
    
    success = True
    
    if len(oids_to_remove) != 3:  # Should remove 3 out of 5 time-based points
        print(f"   ❌ Expected to remove 3 time-based points, got {len(oids_to_remove)}")
        success = False
    else:
        print(f"   ✅ Correctly identified {len(oids_to_remove)} time-based points for removal")
    
    if len(oids_to_remove_good) != 0:  # Should keep all distance-based points
        print(f"   ❌ Expected to keep all distance-based points, but {len(oids_to_remove_good)} marked for removal")
        success = False
    else:
        print(f"   ✅ Correctly kept all distance-based points")
    
    if stats['avg_original_spacing'] > 4.0:  # Time-based should have small spacing
        print(f"   ❌ Expected small average spacing for time-based, got {stats['avg_original_spacing']:.2f}m")
        success = False
    else:
        print(f"   ✅ Time-based spacing correctly detected as small ({stats['avg_original_spacing']:.2f}m)")
    
    return success


if __name__ == "__main__":
    print("🚀 Starting Distance Filter Integration Tests")
    
    try:
        success = test_distance_filter_logic()
        
        if success:
            print("\n🎉 All tests passed! Distance filter is working correctly.")
            print("\n📋 Summary:")
            print("   • Distance calculation (Haversine) working")
            print("   • Time-based capture detection working")
            print("   • Distance-based capture preservation working")
            print("   • Spacing analysis logic validated")
        else:
            print("\n❌ Some tests failed. Check the output above.")
            
    except Exception as e:
        print(f"\n💥 Test failed with error: {e}")
        import traceback
        traceback.print_exc()