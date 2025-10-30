ArcGIS Pro Setup
================

This guide covers the specific steps for setting up the RMI 360 Workflow in ArcGIS Pro.

Prerequisites
-------------

- **ArcGIS Pro 3.4.0** or later (tested with 3.4.3 and 3.5.0)
- **Standard or Advanced license** for Oriented Imagery Dataset (OID) tools
- **Basic license** is sufficient for image processing and enhancement tools

Environment Verification
------------------------

Before adding the main toolbox, verify your Python environment has all required packages.

1. **Add the Environment Checker**

   - Open ArcGIS Pro and load a project (``.aprx`` file)
   - In the **Catalog** pane, right-click **Toolboxes**
   - Select **Add Toolbox**
   - Navigate to and select ``rmi_360_env_checker.pyt``

2. **Run Environment Check**

   - Expand the **RMI 360 Environment Checker** toolbox
   - Double-click **Check Required Python Packages**
   - Review the output to see which packages are available
   - Note any missing packages for installation

3. **Install Missing Packages**

   If packages are missing, install them using one of these methods:

   **Method 1: ArcGIS Pro Package Manager**

   - Go to **Project** → **Python** → **Manage Environments**
   - Select your active environment
   - Click **Add Packages**
   - Search for and install missing packages

   **Method 2: Command Line (if available)**

   .. code-block:: bash

      # Activate ArcGIS Pro environment
      conda activate arcgispro-py3

      # Install packages
      conda install pyyaml boto3 keyring matplotlib

Adding the Main Toolbox
------------------------

1. **Add RMI 360 Workflow Toolbox**

   - In the **Catalog** pane, right-click **Toolboxes**
   - Select **Add Toolbox**
   - Navigate to and select ``rmi_360_workflow.pyt``

2. **Verify Toolbox Structure**

   You should see the following organization:

   .. code-block::

      RMI 360 Workflow
      ├── Setup
      │   ├── Create OID Template Tool
      │   └── Set AWS Keyring Credentials
      ├── Individual Tools
      │   ├── Run Mosaic Processor Tool
      │   ├── Rename and Tag Images
      │   ├── Enhance Images Tool
      │   ├── Smooth GPS Noise Tool
      │   ├── Geocode Images Tool
      │   ├── Create OID Tool
      │   ├── Add Images to OID Tool
      │   ├── Build OID Footprints Tool
      │   ├── Update Linear and Custom Tool
      │   ├── Generate OID Service Tool
      │   ├── Copy to AWS Tool
      │   └── Generate Report Tool
      └── Orchestrator
          └── Process Mosaic 360 Workflow

Troubleshooting
---------------

**Warning Icon (❗) on Toolbox**

If you see a warning icon when the toolbox loads:

1. Right-click the toolbox and select **Remove**
2. Re-add the toolbox using **Add Toolbox**
3. This typically resolves loading issues

**Tool Parameters Not Loading**

If tool parameters appear blank or don't load:

1. Ensure your ArcGIS Pro project is saved
2. Check that you have appropriate license level
3. Verify Python environment has required packages
4. Try closing and reopening ArcGIS Pro

**Python Environment Issues**

If you encounter Python-related errors:

1. Verify your ArcGIS Pro Python environment is active
2. Check Python package installation status
3. Consider creating a fresh environment clone
4. Contact your IT administrator if you lack installation permissions

License Requirements
--------------------

Different tools have different license requirements:

**Basic License (Minimum)**
- Image processing and enhancement
- GPS smoothing and geocoding
- File renaming and metadata tagging
- Report generation
- AWS upload tools

**Standard/Advanced License Required**
- Create OID Tool
- Add Images to OID Tool
- Build OID Footprints Tool
- Generate OID Service Tool
- Any Oriented Imagery Dataset operations

Project Setup Recommendations
-----------------------------

**ArcGIS Pro Project Configuration**

1. **Create a dedicated project** for 360° processing workflows
2. **Set appropriate coordinate system** matching your project area
3. **Add necessary base maps** for spatial reference
4. **Configure folder connections** to your processing directories

**Workspace Organization**

.. code-block::

   Your_360_Project.aprx
   ├── Maps/
   │   ├── Processing_Overview    # For monitoring progress
   │   └── Results_Review        # For reviewing outputs
   ├── Folder Connections/
   │   ├── Process360_Data/      # Main processing directory
   │   └── Config_Files/         # Configuration files
   └── Toolboxes/
       ├── rmi_360_workflow.pyt  # Main workflow
       └── rmi_360_env_checker.pyt  # Environment checker

**Performance Considerations**

- **Close unnecessary applications** during processing
- **Ensure adequate disk space** (processing can require significant storage)
- **Use local drives** rather than network drives when possible
- **Monitor system resources** during long-running operations

Next Steps
----------

After successful ArcGIS Pro setup:

1. Proceed to :doc:`configuration` to set up your project configuration
2. Follow the :doc:`quick-start` guide for your first workflow
3. Review :doc:`../tools/overview` for detailed tool documentation

For additional support, consult your ArcGIS Pro documentation or contact Esri technical support for platform-specific issues.
