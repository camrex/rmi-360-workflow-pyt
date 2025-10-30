Quick Start Guide
================

This guide will help you get started with the RMI 360 Imaging Workflow quickly.

Prerequisites
-------------

Before you begin, ensure you have:

- **ArcGIS Pro 3.4+** installed and licensed
- **Python 3.11+** (included with ArcGIS Pro)
- **Standard or Advanced ArcGIS Pro license** for Oriented Imagery tools
- Access to your 360° video files and calibration data

Step 1: Installation
--------------------

1. **Clone the repository:**

   .. code-block:: bash

      git clone https://github.com/RMI-Valuation/rmi-360-workflow-pyt.git
      cd rmi-360-workflow-pyt

2. **Verify your environment:**

   - Open ArcGIS Pro and load a project
   - Add the environment checker: ``rmi_360_env_checker.pyt``
   - Run **Check Required Python Packages**
   - Install any missing dependencies through ArcGIS Pro Package Manager

3. **Add the main toolbox:**

   - In ArcGIS Pro Catalog, right-click **Toolboxes** → **Add Toolbox**
   - Select ``rmi_360_workflow.pyt``

Step 2: Basic Configuration
---------------------------

1. **Create your config file:**

   .. code-block:: bash

      cp configs/config.sample.yaml configs/config.yaml

2. **Edit essential settings:**

   Open ``configs/config.yaml`` and update:

   .. code-block:: yaml

      project:
        slug: YOUR_PROJECT_ID       # e.g., ABC25110
        number: YOUR_PROJECT_NUM    # e.g., 25-110
        client: Your Client Name
        rr_mark: RR                 # Railroad abbreviation
        rr_name: Railroad Name
        local_proj_wkid: 6492      # Your local projection WKID

      runtime:
        local_root: D:/Process360_Data  # Your processing directory

Step 3: Prepare Your Data
-------------------------

Organize your input data as follows:

.. code-block::

   D:/Process360_Data/projects/YOUR_PROJECT_ID/
   ├── reels/              # Place your .mp4 files here
   │   ├── REEL_001/
   │   ├── REEL_002/
   │   └── ...
   ├── config/             # Optional: project-specific configs
   └── gis_data/          # Optional: GIS reference data

Step 4: Run Your First Workflow
-------------------------------

**Option A: Complete Automated Workflow**

1. Open the **RMI 360 Workflow** toolbox in ArcGIS Pro
2. Navigate to **Orchestrator** → **Process Mosaic 360 Workflow**
3. Fill in the parameters:

   - **Input Folder for Reels**: ``D:/Process360_Data/projects/YOUR_PROJECT_ID/reels``
   - **Project Folder**: ``D:/Process360_Data/projects/YOUR_PROJECT_ID``
   - **Config File**: ``configs/config.yaml``
   - **Mosaic Group File**: Your ``.grp`` calibration file

4. Click **Run** and monitor progress

**Option B: Step-by-Step Workflow**

For more control, run individual tools in sequence:

1. **Run Mosaic Processor Tool** - Process video to panoramic images
2. **Rename and Tag Images Tool** - Apply metadata and rename files
3. **Create OID Tool** - Create Oriented Imagery Dataset
4. **Add Images to OID Tool** - Populate the OID with images
5. **Generate OID Service Tool** - Publish to ArcGIS Portal (optional)

Step 5: Review Results
----------------------

After processing, you'll find:

.. code-block::

   D:/Process360_Data/projects/YOUR_PROJECT_ID/
   ├── panos/
   │   ├── original/        # Raw extracted frames
   │   ├── enhance/         # Enhanced images (if used)
   │   └── final/          # Final renamed images with metadata
   ├── backups/            # OID backup snapshots
   ├── logs/               # Processing logs
   └── report/             # HTML processing report

Common Use Cases
----------------

**Basic 360° Image Processing**
   Use the orchestrator with default settings for standard corridor imaging projects.

**Custom Field Calculations**
   Modify the field registry (``configs/esri_oid_fields_registry.yaml``) to add custom attributes.

**AWS S3 Publishing**
   Configure AWS settings in your config file and use the **Copy to AWS** tool for cloud storage.

**Portal Publishing**
   Set up ArcGIS Portal credentials and use **Generate OID Service** for web publishing.

Next Steps
----------

- Review the :doc:`../config/overview` for detailed configuration options
- Explore :doc:`../tools/overview` for individual tool documentation
- Check :doc:`../aws/setup-guide` for cloud integration setup

Troubleshooting
---------------

**Common Issues:**

- **Tool won't load**: Remove and re-add the toolbox in ArcGIS Pro
- **Missing packages**: Run the environment checker and install missing dependencies
- **Processing fails**: Check the log files in your project's ``logs/`` directory
- **Configuration errors**: Validate your YAML syntax and required fields

For more help, see the complete documentation sections or check the project logs for detailed error messages.
