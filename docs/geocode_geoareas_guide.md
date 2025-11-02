# Corridor Geo-Areas Enrichment

## Overview

The Corridor Geo-Areas Enrichment utility provides advanced geographic context for corridor photo points by combining polygon containment analysis with milepost-based intelligence. This enrichment runs **before** ExifTool tagging to ensure all geographic area data is available for EXIF metadata application in a single batch operation.

## Features

### Core Enrichment Capabilities
- **Polygon Containment**: Direct spatial joins with Places and Counties feature classes
- **Milepost Context**: Prev/next/nearest place context based on route mileposts  
- **Gap Bridging**: Intelligent inference for short gaps between same-place anchors
- **Range Building**: Contiguous place ranges from anchor points for comprehensive coverage
- **Nearest Promotion**: Optional promotion of nearby places within threshold distance

### Data Quality & Provenance
- **Source Tracking**: Every enriched value includes provenance (CONTAINED, INFERRED_BRIDGE, RANGE_LOOKUP, etc.)
- **QA Reporting**: Detailed CSV reports with counts and example OIDs for each enrichment type
- **Idempotent Operation**: Safe to re-run without data corruption or duplication

## Usage

### ArcGIS Pro Tool

The "08 - Geocode Geo-Areas" tool provides a graphical interface for the enrichment process:

1. **Photos Feature Class**: Point FC containing corridor photos with milepost data
2. **Places Feature Class**: Polygon FC with place boundaries (recommend Living Atlas)
3. **Counties Feature Class**: Polygon FC with county boundaries (recommend Living Atlas)
4. **Processing Mode**: Choose level of enrichment from basic to full workflow
5. **Parameters**: Configure gap bridging, range building, and promotion settings

### Configuration-Based Usage

Add geo-areas settings to your `config.yaml`:

```yaml
geo_areas:
  enabled: true
  mode: "FULL"  
  mile_field: "milepost"
  route_field: "route_id"
  max_gap_miles: 1.0
  places_fc: "gis_data/reference.gdb/USA_Places"
  counties_fc: "gis_data/reference.gdb/USA_Counties"
  write_report_csv: true
```

### Programmatic Usage

```python
from utils.geocode_geoareas import geocode_geoareas

results = geocode_geoareas(
    photos_fc="path/to/photos.shp",
    places_fc="path/to/places.shp", 
    counties_fc="path/to/counties.shp",
    mile_field="milepost",
    route_field="route_id",
    max_gap_miles=1.0,
    promote_nearest_to_actual=False,
    logger=print
)
```

## Output Fields

The enrichment process adds the following fields to your photos feature class:

### Geographic Context
- `geo_place` (TEXT): Place name from containment or inference
- `geo_place_fips` (TEXT): FIPS code for the place
- `geo_county` (TEXT): County name 
- `geo_county_fips` (TEXT): County FIPS code
- `geo_state` (TEXT): State name or abbreviation
- `geo_state_fips` (TEXT): State FIPS code

### Provenance & Quality
- `geo_place_source` (TEXT): Source of place assignment
  - `CONTAINED`: Direct polygon containment
  - `INFERRED_BRIDGE`: Gap-bridged between same places
  - `RANGE_LOOKUP`: Assigned from place range
  - `NEAREST_ALONG`: Promoted from nearest place
  - `COUNTY_ONLY`: Only county/state available
- `geo_place_inferred` (SHORT): 0=direct, 1=inferred
- `geo_place_gap_miles` (DOUBLE): Gap distance when bridged

### Milepost Context  
- `geo_prev_place` (TEXT): Previous place along route
- `geo_prev_miles` (DOUBLE): Distance to previous place
- `geo_next_place` (TEXT): Next place along route  
- `geo_next_miles` (DOUBLE): Distance to next place
- `geo_nearest_place` (TEXT): Nearest place (up or down route)
- `geo_nearest_miles` (DOUBLE): Distance to nearest place
- `geo_nearest_dir` (TEXT): Direction to nearest (UP/DN)

## Integration with ExifTool

The enriched geo-area data integrates seamlessly with ExifTool metadata tagging:

### Standard EXIF Tags
- `City` → `geo_place`
- `State` → `geo_state` 
- `Country` → "United States"

### Enhanced Context in Comments
When `geo_place` is null, XPComment automatically includes context:
```
" near {geo_nearest_place} ({geo_nearest_dir} {geo_nearest_miles:.1f} mi)"
```

Example: `"MP 45.2 near Springfield (UP 2.3 mi)"`

## Processing Modes

### CONTAINMENT_ONLY
- Performs only polygon containment joins
- Fills place, county, state from direct spatial relationships
- Fastest option, minimal inference

### CONTAINMENT+MILEPOST_CONTEXT  
- Adds prev/next/nearest context calculation
- Provides milepost-aware geographic context
- Good for basic corridor awareness

### CONTAINMENT+MILEPOST+GAP_BRIDGE
- Includes gap bridging for short slivers
- Infers places for points between same-place anchors
- Reduces "unknown" areas in continuous corridors

### CONTAINMENT+RANGES_BUILD_APPLY
- Builds and applies place-milepost ranges
- Comprehensive coverage using anchor extrapolation
- Good for sparse place data

### FULL (Recommended)
- Complete enrichment workflow
- All containment, context, bridging, and range operations
- Maximum geographic context and coverage

## Data Requirements

### Photos Feature Class
- **Geometry**: Point features
- **Required Fields**: Numeric milepost field
- **Optional Fields**: Route ID for multi-route projects
- **Spatial Reference**: Any (will be reprojected as needed)

### Places Feature Class  
- **Geometry**: Polygon features (cities, towns, CDPs)
- **Required Fields**: NAME or similar for place names
- **Optional Fields**: GEOID/FIPS for place codes
- **Recommended**: Esri Living Atlas USA Places

### Counties Feature Class
- **Geometry**: Polygon features 
- **Required Fields**: NAME for county names
- **Required Fields**: STUSPS or similar for state info
- **Optional Fields**: GEOID/FIPS for county codes
- **Recommended**: Esri Living Atlas USA Counties

## Performance Considerations

### Optimization Strategies
- **O(N log N) per route**: Efficient milepost sorting and lookup
- **Cached anchor arrays**: Avoids repeated list scans
- **Attribute-based operations**: Minimal geometry processing after spatial joins

### Scalability
- **100k+ points**: Comfortable processing for large corridors  
- **Multiple routes**: Parallel processing by route_id
- **Memory efficient**: Streaming operations where possible

## Quality Assurance

### Built-in Validation
- Input feature class validation (geometry, fields, spatial reference)
- Parameter range checking (gap distances, thresholds)
- Living Atlas field mapping detection

### QA Reporting
Generated CSV report includes:
- Counts by enrichment type (contained, bridged, range-filled, etc.)
- Example OIDs for each category (up to 10 per type)
- Processing statistics and timing information

### Idempotent Design
- Safe to re-run multiple times
- Only fills null/empty values unless explicitly overridden
- Preserves existing user-assigned values

## Configuration Integration

### Geocoding Method Selection

The geo-areas enrichment integrates with the existing geocoding system through the `geocoding.method` setting:

```yaml
geocoding:
  method: "geo_areas"  # Options: "exiftool", "geo_areas", "both"
```

**Method Options:**
- **`"exiftool"`**: Uses only ExifTool's internal reverse geocoding (original behavior)
- **`"geo_areas"`**: Uses only corridor geo-areas enrichment with Living Atlas data
- **`"both"`**: Applies geo-areas enrichment first, then ExifTool reverse geocoding (recommended for comprehensive tagging)

### ExifTool Integration

When using `"geo_areas"` or `"both"` methods, the enriched geographic data is automatically integrated into the ExifTool metadata workflow. The system adds comprehensive location tags to your images:

**EXIF Tags Added:**
- `City` - Place name with configurable fallback
- `State` - State name from county data
- `Country` - Always "United States"
- `CountryCode` - Always "US"

**XMP IPTC Core Tags:**
- `CountryCode` - Always "US"

**XMP IPTC Extension Tags:**
- `LocationShownCity` - Place name with descriptive fallbacks
- `LocationShownCountryCode` - Always "US"
- `LocationShownCountryName` - Always "United States"
- `LocationShownProvinceState` - State name
- `LocationShownGPSLatitude` - GPS latitude
- `LocationShownGPSLongitude` - GPS longitude

**XMP Photoshop Tags:**
- `City` - Place name with fallback
- `Country` - Always "United States"  
- `State` - State name

### Fallback Strategy Configuration

For points outside place boundaries, the system provides configurable fallback behavior:

```yaml
geo_areas:
  city_fallback_strategy: "nearest_then_county"  # Options below
  include_nearest_indicator: true                 # Add "(nearest)" suffix
```

**Strategy Options:**
- `"county_only"`: Use county name (e.g., "Adams County")
- `"nearest_only"`: Use nearest place (e.g., "Springfield (nearest)")
- `"nearest_then_county"`: Try nearest place, then county (recommended)

## Advanced Configuration

### Gap Bridging Tuning
```yaml
max_gap_miles: 1.0      # Maximum distance to bridge
break_gap_miles: 0.5    # Range continuity break threshold
min_points_per_range: 2 # Minimum anchor points for valid range
```

### Nearest Place Promotion
```yaml
promote_nearest_to_actual: true
max_nearest_miles: 2.0  # Maximum promotion distance
```

### Custom Data Sources
```yaml
places_fc: "custom_data/corridor_places.shp"
counties_fc: "custom_data/enhanced_counties.shp"
corridor_places_fc: "custom_data/buffered_places.shp"  # Future use
```

## Error Handling & Troubleshooting

### Common Issues
1. **Missing milepost field**: Tool will skip milepost-based enrichment
2. **Non-monotonic mileposts**: Stable sort handles ties using OID
3. **Sparse anchor coverage**: Ranges require minimum point thresholds
4. **Coordinate system differences**: Automatic reprojection handles most cases

### Debug Mode
Enable detailed logging in config:
```yaml
debug_messages: true
```

### Validation Messages
The tool provides specific warnings for:
- Missing or incorrect field types
- Empty feature classes
- Spatial reference issues
- Parameter range violations

## Best Practices

### Data Preparation
1. **Cache Living Atlas data locally** for better performance
2. **Validate milepost continuity** before enrichment
3. **Review route_id assignment** for multi-route corridors
4. **Consider corridor buffering** for places data if needed

### Workflow Integration
1. **Run after milepost assignment** but before ExifTool tagging
2. **Review QA report** to understand enrichment patterns
3. **Adjust parameters** based on corridor characteristics
4. **Backup feature class** before first run

### Performance Optimization
1. **Use file geodatabase** format for better performance
2. **Index milepost and route fields** for large datasets  
3. **Consider spatial indexing** on places and counties
4. **Run CONTAINMENT_ONLY first** to assess coverage before full enrichment