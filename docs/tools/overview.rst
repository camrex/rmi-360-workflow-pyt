Tools Overview
==============

The RMI 360 Imaging Workflow provides a comprehensive set of ArcGIS Python Toolbox tools organized into three main categories.

Tool Categories
---------------

Setup Tools
^^^^^^^^^^^

These tools help you prepare your environment and configure initial settings.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Tool Name
     - Purpose
   * - Create OID Template Tool
     - Creates geodatabase templates and schema for Oriented Imagery Datasets
   * - Set AWS Keyring Credentials
     - Securely stores AWS credentials for S3 upload operations

Individual Processing Tools
^^^^^^^^^^^^^^^^^^^^^^^^^^^

These tools perform specific processing steps that can be run individually or in sequence.

**Image and Video Processing**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Tool Name
     - Purpose
   * - Run Mosaic Processor Tool
     - Processes 360° video files using Mosaic Processor to extract panoramic images
   * - Rename and Tag Images
     - Applies EXIF metadata and renames images according to configuration rules
   * - Enhance Images Tool
     - Applies image enhancement (contrast, white balance, sharpening)

**GPS and Spatial Processing**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Tool Name
     - Purpose
   * - Smooth GPS Noise Tool
     - Reduces GPS noise and removes outliers from position data
   * - Geocode Images Tool
     - Assigns spatial attributes based on GIS reference datasets

**OID Creation and Management**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Tool Name
     - Purpose
   * - Create OID Tool
     - Creates new Oriented Imagery Dataset feature classes
   * - Add Images to OID Tool
     - Populates OID with processed panoramic images
   * - Build OID Footprints Tool
     - Generates spatial footprints for OID coverage areas
   * - Update Linear and Custom Tool
     - Calculates linear referencing and custom field values

**Publishing and Output**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Tool Name
     - Purpose
   * - Generate OID Service Tool
     - Publishes OID to ArcGIS Portal as a web service
   * - Copy to AWS Tool
     - Uploads processed files to Amazon S3 storage
   * - Generate Report Tool
     - Creates HTML reports summarizing processing results

Orchestrator
^^^^^^^^^^^^

The orchestrator provides automated end-to-end workflow execution.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Tool Name
     - Purpose
   * - Process Mosaic 360 Workflow
     - Runs the complete workflow from raw video to published OID service

Typical Workflow Sequence
--------------------------

**Standard Processing Order:**

1. **Run Mosaic Processor Tool** - Extract panoramic images from 360° video
2. **Rename and Tag Images** - Apply metadata and standardized naming
3. **Smooth GPS Noise Tool** - Clean and smooth GPS positioning data
4. **Geocode Images Tool** *(optional)* - Add spatial attributes from reference data
5. **Enhance Images Tool** *(optional)* - Apply image enhancement
6. **Create OID Tool** - Create Oriented Imagery Dataset
7. **Add Images to OID Tool** - Populate OID with processed images
8. **Build OID Footprints Tool** - Generate coverage footprints
9. **Update Linear and Custom Tool** - Calculate additional attributes
10. **Generate OID Service Tool** *(optional)* - Publish to Portal
11. **Copy to AWS Tool** *(optional)* - Upload to cloud storage
12. **Generate Report Tool** - Create processing summary

**Orchestrator Alternative:**

Instead of running individual tools, use **Process Mosaic 360 Workflow** to execute the entire sequence automatically with a single tool run.

Common Usage Patterns
----------------------

**Basic Corridor Imaging**
   Use orchestrator with default settings for standard highway/railroad corridor documentation.

**Research and Analysis**
   Run individual tools to experiment with different processing parameters and review intermediate results.

**Production Workflows**
   Combine orchestrator for primary processing with individual tools for specific customizations or corrections.

**Quality Control**
   Use individual tools to reprocess specific steps without repeating the entire workflow.

Tool Parameters
---------------

Most tools share common parameter patterns:

**Required Parameters:**
- Input data paths (images, videos, or feature classes)
- Configuration file path
- Output locations

**Optional Parameters:**
- Processing flags (dry run, skip existing, etc.)
- Advanced settings (thresholds, quality settings)
- Integration options (AWS, Portal credentials)

**Configuration-Driven:**
Many tool behaviors are controlled by the YAML configuration file rather than individual parameters, providing consistency and repeatability across projects.

Next Steps
----------

- Review :doc:`setup-tools` for environment preparation
- See :doc:`individual-tools` for detailed tool documentation
- Learn about :doc:`orchestrator` for automated processing
- Check the :doc:`../api/tools` for technical implementation details
