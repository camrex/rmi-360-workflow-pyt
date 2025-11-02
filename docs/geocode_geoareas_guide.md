# Corridor Geo-Areas Enrichment

## Overview

The Corridor Geo-Areas Enrichment Utility provides advanced geographic context for railway corridor imagery beyond simple reverse geocoding. It enriches photo points with:

- **Place containment** using Living Atlas places data
- **County and state information** from administrative boundaries  
- **Efficient range-based enrichment** for comprehensive corridor coverage
- **Intelligent gap bridging** between discontinuous place segments
- **Multi-tier verification** with comprehensive source tracking

### Processing Modes

The system offers multiple processing modes optimized for different use cases:

- **`CONTAINMENT+RANGES_BUILD_APPLY`** (Recommended): Most efficient approach that performs polygon containment then builds comprehensive mile ranges for complete coverage
- **`FULL`**: Legacy comprehensive mode that includes redundant individual milepost enrichment before range building
- **`CONTAINMENT_ONLY`**: Basic polygon joins only
- **Other modes**: Available for specialized workflows or debugging

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
- `geo_county_fips` (TEXT): 5-digit county FIPS code (first 2 digits = state FIPS)
- `geo_state` (TEXT): State name or abbreviation

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
- `geo_prev_place` (TEXT): Previous place along route (lower milepost)
- `geo_prev_miles` (DOUBLE): Distance to previous place
- `geo_next_place` (TEXT): Next place along route (higher milepost)
- `geo_next_miles` (DOUBLE): Distance to next place

**Note**: Nearest place and directional context (e.g., "east of Springfield") are calculated dynamically at runtime by comparing `geo_prev_miles` vs `geo_next_miles` using the configured milepost directions.

## Integration with ExifTool

The enriched geo-area data integrates seamlessly with ExifTool metadata tagging:

### Standard EXIF Tags
- `City` → `geo_place`
- `State` → `geo_state` 
- `Country` → "United States"

### Enhanced Context in Comments
When `geo_place` is null, XPComment automatically includes context with dynamically calculated nearest place and direction:
```
" near {nearest_place} ({direction} {nearest_miles:.1f} mi)"
```

Example: `"MP 45.2 near Springfield (UP 2.3 mi)"` where nearest place and direction are computed at runtime from prev/next place distances

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
  method: "geo_areas"  # Options: "exiftool", "geo_areas" (mutually exclusive)
```

**Method Options:**
- **`"exiftool"`**: Uses only ExifTool's internal reverse geocoding (original behavior)
- **`"geo_areas"`**: Uses only corridor geo-areas enrichment with Living Atlas data (recommended)


### ExifTool Integration

When using the `"geo_areas"` method, the enriched geographic data is automatically integrated into the ExifTool metadata workflow. The system adds comprehensive location tags to your images:

**Note**: Methods are mutually exclusive - ExifTool geocoding would overwrite geo-areas EXIF data, so only one method can be active per workflow run.

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

### XPKeywords Enrichment

The system automatically enhances XPKeywords with additional geographic context:

```yaml
geo_areas:
  include_county_keyword: true                    # Add county names to XPKeywords
  include_directional_context: true              # Add directional descriptions for points outside places
  milepost_directions:
    increasing_direction: "west"                  # Direction for increasing mileposts
    decreasing_direction: "east"                  # Direction for decreasing mileposts
```

**Enhanced XPKeywords Examples:**
- County context: `"Adams County"`, `"Cook County"`
- Directional context: `"2.4 miles west of Sedalia"`, `"1.7 miles east of Springfield"`

**Milepost-Based Directions:**
Railroad corridors use operational directions based on milepost progression rather than cardinal directions. Configure the `milepost_directions` to match your railroad's milepost system:
- If mileposts increase westbound, set `increasing_direction: "west"`
- The system calculates direction by comparing distances to prev/next places
- If closer to prev_place (lower milepost), uses `decreasing_direction`
- If closer to next_place (higher milepost), uses `increasing_direction`
- Example: Point 2.1 miles from prev place vs. 3.4 miles from next place = "2.1 miles east of [prev_place]"

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

## Schema Evolution

### Removed Fields
The following fields were removed in recent optimizations for efficiency and reduced redundancy:

- **`geo_state_fips`**: Removed as redundant - state FIPS code is available as the first 2 digits of `geo_county_fips`
- **`geo_nearest_dir`**: Removed in favor of dynamic calculation - directional context is now computed by comparing `geo_prev_miles` vs `geo_next_miles` using configured milepost directions
- **`geo_nearest_place`**: Removed in favor of dynamic calculation - nearest place is determined at runtime by comparing distances in `geo_prev_miles` vs `geo_next_miles`
- **`geo_nearest_miles`**: Removed in favor of dynamic calculation - nearest distance is determined at runtime from the closer of `geo_prev_miles` or `geo_next_miles`

These optimizations streamline the schema while maintaining all necessary geographic context through more efficient field relationships and runtime calculations.

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