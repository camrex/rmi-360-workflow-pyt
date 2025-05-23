# ArcPy Function Licensing Matrix

> **Document Location:** `docs_legacy/ARCGISPRO_LICENSE_REQUIREMENTS.md`  
> **Generated:** 2025-05-23

This document summarizes the **ArcPy functions and classes used in this project**, along with the minimum required ArcGIS Pro license level (Basic, Standard, Advanced) for each. Use this table to identify tools that may require higher license tiers and ensure your deployment environment is compatible.

**Note:**
- License requirements are based on [Esri’s ArcGIS Pro documentation](https://pro.arcgis.com/).
- Requirements can change between ArcGIS Pro versions—always check the [official tool documentation](https://pro.arcgis.com/en/pro-app/latest/tool-reference/main/license-requirements-by-tool.htm) for the most current details.
- This table was generated for RMI 360 Imaging Workflow Toolbox v1.x.


## All ArcPy functions/classes used in this project

| Function/Class                                           | Basic | Standard | Advanced |
|----------------------------------------------------------|:-----:|:--------:|:--------:|
| `arcpy.AddError`                                         | ✅    | ✅       | ✅       |
| `arcpy.AddMessage`                                       | ✅    | ✅       | ✅       |
| `arcpy.AddWarning`                                       | ✅    | ✅       | ✅       |
| `arcpy.CreateUniqueName`                                 | ✅    | ✅       | ✅       |
| `arcpy.Describe`                                         | ✅    | ✅       | ✅       |
| `arcpy.ExecuteError`                                     | ✅    | ✅       | ✅       |
| `arcpy.Exists`                                           | ✅    | ✅       | ✅       |
| `arcpy.GetMessages`                                      | ✅    | ✅       | ✅       |
| `arcpy.ListFields`                                       | ✅    | ✅       | ✅       |
| `arcpy.Point`                                            | ✅    | ✅       | ✅       |
| `arcpy.PointGeometry`                                    | ✅    | ✅       | ✅       |
| `arcpy.ResetProgressor`                                  | ✅    | ✅       | ✅       |
| `arcpy.SetProgressor`                                    | ✅    | ✅       | ✅       |
| `arcpy.SetProgressorLabel`                               | ✅    | ✅       | ✅       |
| `arcpy.SetProgressorPosition`                            | ✅    | ✅       | ✅       |
| `arcpy.SpatialReference`                                 | ✅    | ✅       | ✅       |
| `arcpy.da.SearchCursor`                                  | ✅    | ✅       | ✅       |
| `arcpy.da.UpdateCursor`                                  | ✅    | ✅       | ✅       |
| `arcpy.env.geographicTransformations`                    | ✅    | ✅       | ✅       |
| `arcpy.env.outputCoordinateSystem`                       | ✅    | ✅       | ✅       |
| `arcpy.env.scratchGDB`                                  | ✅    | ✅       | ✅       |
| `arcpy.management.AddField`                              | ✅    | ✅       | ✅       |
| `arcpy.management.Copy`                                  | ✅    | ✅       | ✅       |
| `arcpy.management.CreateFileGDB`                         | ✅    | ✅       | ✅       |
| `arcpy.management.CreateTable`                           | ✅    | ✅       | ✅       |
| `arcpy.management.Delete`                                | ✅    | ✅       | ✅       |
| `arcpy.management.GetCount`                              | ✅    | ✅       | ✅       |
| `arcpy.management.Project`                               | ✅    | ✅       | ✅       |
| `arcpy.management.Rename`                                | ✅    | ✅       | ✅       |
| `arcpy.lr.LocateFeaturesAlongRoutes`                     | ✅    | ✅       | ✅       |
| `arcpy.oi.AddImagesToOrientedImageryDataset`             |       | ✅       | ✅       |
| `arcpy.oi.BuildOrientedImageryFootprint`                 |       | ✅       | ✅       |
| `arcpy.oi.CreateOrientedImageryDataset`                  |       | ✅       | ✅       |
| `arcpy.oi.GenerateServiceFromOrientedImageryDataset`     |       | ✅       | ✅       |

> ℹ️ The “Oriented Imagery” tools require **Standard or Advanced** licenses. All other functions are available with **Basic** or higher.

---

## ArcPy usage by file

### `..\rmi_360_env_checker.pyt`
- `arcpy.AddError`
- `arcpy.AddMessage`
- `arcpy.AddWarning`

### `..\utils\add_images_to_oid_fc.py`
- `arcpy.ExecuteError`
- `arcpy.Exists`
- `arcpy.oi.AddImagesToOrientedImageryDataset`

### `..\utils\apply_exif_metadata.py`
- `arcpy.ListFields`
- `arcpy.da.SearchCursor`

### `..\utils\assign_group_index.py`
- `arcpy.ListFields`
- `arcpy.da.SearchCursor`
- `arcpy.da.UpdateCursor`

### `..\utils\build_oid_footprints.py`
- `arcpy.Describe`
- `arcpy.Exists`
- `arcpy.SpatialReference`
- `arcpy.env.geographicTransformations`
- `arcpy.env.outputCoordinateSystem`
- `arcpy.oi.BuildOrientedImageryFootprint`

### `..\utils\build_oid_schema.py`
- `arcpy.Exists`
- `arcpy.ListFields`
- `arcpy.management.AddField`
- `arcpy.management.CreateFileGDB`
- `arcpy.management.CreateTable`
- `arcpy.management.Rename`

### `..\utils\calculate_oid_attributes.py`
- `arcpy.da.SearchCursor`
- `arcpy.da.UpdateCursor`
- `arcpy.management.GetCount`

### `..\utils\correct_gps_outliers.py`
- `arcpy.da.SearchCursor`
- `arcpy.da.UpdateCursor`

### `..\utils\create_oid_feature_class.py`
- `arcpy.ExecuteError`
- `arcpy.Exists`
- `arcpy.SpatialReference`
- `arcpy.oi.CreateOrientedImageryDataset`

### `..\utils\enhance_images.py`
- `arcpy.da.SearchCursor`
- `arcpy.da.UpdateCursor`

### `..\utils\generate_oid_service.py`
- `arcpy.Exists`
- `arcpy.GetMessages`
- `arcpy.da.UpdateCursor`
- `arcpy.management.Copy`
- `arcpy.management.Delete`
- `arcpy.oi.GenerateServiceFromOrientedImageryDataset`

### `..\utils\geocode_images.py`
- `arcpy.da.SearchCursor`

### `..\utils\manager\progressor_manager.py`
- `arcpy.ResetProgressor`
- `arcpy.SetProgressor`
- `arcpy.SetProgressorLabel`
- `arcpy.SetProgressorPosition`

### `..\utils\rename_images.py`
- `arcpy.ListFields`
- `arcpy.da.UpdateCursor`

### `..\utils\shared\check_disk_space.py`
- `arcpy.da.SearchCursor`

### `..\utils\shared\gather_metrics.py`
- `arcpy.da.SearchCursor`

### `..\utils\shared\schema_validator.py`
- `arcpy.Exists`
- `arcpy.ListFields`

### `..\utils\smooth_gps_noise.py`
- `arcpy.ListFields`
- `arcpy.Point`
- `arcpy.PointGeometry`
- `arcpy.SpatialReference`
- `arcpy.da.SearchCursor`
- `arcpy.da.UpdateCursor`
- `arcpy.management.AddField`

### `..\utils\update_linear_and_custom.py`
- `arcpy.CreateUniqueName`
- `arcpy.Describe`
- `arcpy.da.SearchCursor`
- `arcpy.da.UpdateCursor`
- `arcpy.env.scratchGDB`
- `arcpy.lr.LocateFeaturesAlongRoutes`
- `arcpy.management.GetCount`
- `arcpy.management.Project`

