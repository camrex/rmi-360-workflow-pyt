Configuration
=============

Overview
--------

The RMI 360 Imaging Workflow is driven by a YAML configuration file that controls all aspects of processing. The configuration file defines project metadata, processing parameters, file paths, AWS settings, and field mappings.

Configuration File Structure
----------------------------

The main configuration file (``config.yaml``) contains several top-level sections:

.. code-block:: yaml

   project:             # Project metadata and identifiers
   camera_offset:       # Camera height and Z-offset configuration
   image_output:        # Output folder structure and filename patterns
   gps_smoothing:       # GPS deviation and outlier detection
   oid_schema_template: # OID field definitions and templates
   logs:               # Logging configuration
   executables:        # Paths to external tools
   aws:                # AWS S3 and Lambda configuration
   portal:             # ArcGIS Portal settings (optional)
   geocoding:          # Spatial reference datasets (optional)
   report:             # HTML report generation settings

Getting Started
---------------

1. **Copy the Sample Configuration:**

   .. code-block:: bash

      cp configs/config.sample.yaml configs/config.yaml

2. **Edit the Configuration:**

   Open ``configs/config.yaml`` in your preferred text editor and customize the settings for your project.

Key Configuration Sections
---------------------------

Project Settings
^^^^^^^^^^^^^^^^

Define basic project information:

.. code-block:: yaml

   project:
     slug: ABC25110              # Short project identifier
     number: 25-110              # Project number
     client: Test Client         # Client name
     rr_mark: TC                 # Railroad mark/abbreviation
     rr_name: Test Railroad      # Full railroad name
     description: Hi-Rail Test   # Project description
     local_proj_wkid: 6492      # Local projection WKID

Runtime Configuration
^^^^^^^^^^^^^^^^^^^^^

Specify processing paths and runtime settings:

.. code-block:: yaml

   runtime:
     local_root: D:/Process360_Data    # Base directory for all processing

Camera and GPS Settings
^^^^^^^^^^^^^^^^^^^^^^^

Configure camera offset and GPS smoothing:

.. code-block:: yaml

   camera_offset:
     z_offset: 0.0               # Vertical offset in meters
     camera_height: 3.5          # Camera height above ground

   gps_smoothing:
     deviation_threshold: 50.0   # GPS deviation threshold in meters
     outlier_detection: true     # Enable outlier detection

Image Output Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^

Control output folder structure and file naming:

.. code-block:: yaml

   image_output:
     folders:
       parent: panos             # Base folder name
       original: original        # Raw images subfolder
       enhanced: enhance         # Enhanced images subfolder
       renamed: final           # Final renamed images subfolder

     filename_settings:
       format: "{project_slug}_{rr}_{mp_pre}{mp_num}_{capture_datetime}_RL{reel}_FR{frame}.jpg"
       parts:
         project_slug: "config.project.slug"
         rr: "field.RR"
         # ... additional filename components

AWS Configuration
^^^^^^^^^^^^^^^^^

Configure AWS S3 uploads and Lambda monitoring:

.. code-block:: yaml

   aws:
     s3:
       bucket_name: rmi-360-raw
       region: us-east-1
       prefix: "{project.slug}"

     lambda:
       function_name: rmi-360-upload-monitor
       schedule_expression: "rate(5 minutes)"

Field Registry
--------------

The workflow uses a field registry system to define OID schema fields. This is controlled by:

.. code-block:: yaml

   oid_schema_template:
     esri_default:
       field_registry: configs/esri_oid_fields_registry.yaml

The field registry defines:

- Field names, types, and properties
- Default values and calculations
- Field aliases and descriptions
- Validation rules

Configuration Validation
------------------------

The workflow includes built-in configuration validation:

1. **Required Fields:** All mandatory configuration sections must be present
2. **Path Validation:** File and folder paths are checked for existence
3. **WKID Validation:** Spatial reference system codes are verified
4. **AWS Credentials:** S3 and Lambda settings are validated (when used)

Environment-Specific Configs
-----------------------------

You can maintain separate configurations for different environments:

.. code-block:: bash

   configs/
   ├── config.yaml              # Main configuration
   ├── config.sample.yaml       # Template
   ├── config.dev.yaml          # Development settings
   ├── config.prod.yaml         # Production settings
   └── esri_oid_fields_registry.yaml

Advanced Configuration
----------------------

Expression Resolution
^^^^^^^^^^^^^^^^^^^^^

The configuration system supports expression resolution for dynamic values:

.. code-block:: yaml

   # Reference other config values
   derived_value: "{project.slug}_{project.number}"

   # Reference field values (during processing)
   calculated_field: "field.Reel * 1000 + field.Frame"

Template Customization
^^^^^^^^^^^^^^^^^^^^^^

Customize HTML report templates and OID schema templates by modifying files in the ``templates/`` directory.

Configuration Best Practices
-----------------------------

1. **Version Control:** Keep your configuration files in version control
2. **Environment Separation:** Use separate configs for dev/test/production
3. **Sensitive Data:** Use environment variables or keyring for AWS credentials
4. **Documentation:** Comment your configuration changes
5. **Validation:** Always test configuration changes with sample data

Troubleshooting
---------------

**Configuration Validation Errors**
   Check the log output for specific validation failures and correct the configuration accordingly.

**Path Resolution Issues**
   Ensure all file and folder paths use forward slashes (/) or properly escaped backslashes (\\\\) on Windows.

**YAML Syntax Errors**
   Use a YAML validator to check syntax. Common issues include incorrect indentation and unquoted special characters.

Next Steps
----------

After configuring your project settings, proceed to :doc:`quick-start` to begin processing your first dataset.
