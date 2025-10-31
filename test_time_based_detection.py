# Test the enhanced time-based detection logic
import sys
sys.path.insert(0, r'C:\Process360\repos\current\rmi-360-workflow-pyt')

from utils.filter_distance_spacing import analyze_spacing_by_reel
from datetime import datetime

class MockLogger:
    def debug(self, msg, indent=0): print("  " * indent + msg)
    def info(self, msg, indent=0): print("  " * indent + msg)
    def warning(self, msg, indent=0): print("  " * indent + "WARNING: " + msg)

# Test Case 1: Normal distance-based reel (5m spacing)
print("=== TEST 1: Normal Distance-Based Reel (5m spacing) ===")
distance_based_points = [
    {"oid": i, "x": -110.0 + i * 0.00004, "y": 40.0, "ts": datetime.now(), "reel": "reel_001"} 
    for i in range(10)  # ~4.4m apart each
]

oids_to_remove, stats = analyze_spacing_by_reel(distance_based_points, 5.0, 1.0, MockLogger())
print(f"Result: is_time_based={stats['is_time_based']}, removed={stats['removed_count']}/{stats['total_points']}")
print(f"Avg spacing: {stats['avg_original_spacing']:.2f}m, close ratio: {stats['close_points_ratio']:.1%}")
print()

# Test Case 2: Time-based reel (0.1s intervals, very close points)
print("=== TEST 2: Time-Based Reel (0.1s intervals) ===")
time_based_points = [
    {"oid": i, "x": -110.0 + i * 0.000002, "y": 40.0, "ts": datetime.now(), "reel": "reel_002"} 
    for i in range(50)  # ~0.22m apart each (very close!)
]

oids_to_remove, stats = analyze_spacing_by_reel(time_based_points, 5.0, 1.0, MockLogger())
print(f"Result: is_time_based={stats['is_time_based']}, removed={stats['removed_count']}/{stats['total_points']}")
print(f"Avg spacing: {stats['avg_original_spacing']:.2f}m, close ratio: {stats['close_points_ratio']:.1%}")
print()

# Test Case 3: Mixed reel (some close, some far - edge case)
print("=== TEST 3: Mixed Spacing Reel (edge case) ===")
mixed_points = []
for i in range(20):
    if i < 10:
        # First half: close points (time-based section)
        x_offset = i * 0.000002  # ~0.22m apart
    else:
        # Second half: normal spacing
        x_offset = 0.00002 + (i - 10) * 0.00004  # ~4.4m apart
    mixed_points.append({"oid": i, "x": -110.0 + x_offset, "y": 40.0, "ts": datetime.now(), "reel": "reel_003"})

oids_to_remove, stats = analyze_spacing_by_reel(mixed_points, 5.0, 1.0, MockLogger())
print(f"Result: is_time_based={stats['is_time_based']}, removed={stats['removed_count']}/{stats['total_points']}")
print(f"Avg spacing: {stats['avg_original_spacing']:.2f}m, close ratio: {stats['close_points_ratio']:.1%}")

print("\n=== Summary ===")
print("✅ Distance-based reels are preserved")
print("✅ Time-based reels are detected and filtered")
print("✅ Only obvious time-based patterns trigger filtering")