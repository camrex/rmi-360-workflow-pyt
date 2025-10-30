Installation
============

Requirements
------------

The RMI 360 Imaging Workflow requires:

- **ArcGIS Pro 3.4.0** or later (tested with 3.4.3 and 3.5.0)
- **Python 3.11+** (included with ArcGIS Pro)
- **Standard or Advanced ArcGIS Pro license** (for Oriented Imagery tools)

Python Dependencies
-------------------

The following Python packages are required and should be available in your ArcGIS Pro environment:

.. code-block:: text

   pyyaml          # YAML parsing (used for config files)
   boto3           # AWS SDK for Python
   botocore        # Core dependency for boto3
   keyring         # Secure credential storage
   numpy           # Numerical computing
   jinja2          # Templating for reports or config generation
   pytest          # Unit testing
   matplotlib      # Plotting and visualization

Installing Dependencies
-----------------------

Most dependencies are already included with ArcGIS Pro. For any missing packages:

1. **Using ArcGIS Pro Package Manager:**

   - Open ArcGIS Pro
   - Go to **Project** → **Python** → **Manage Environments**
   - Select your environment and click **Add Packages**
   - Search for and install required packages

2. **Using Conda (if available):**

   .. code-block:: bash

      conda activate <your-arcgis-environment>
      conda install pyyaml boto3 keyring matplotlib

3. **Using pip:**

   .. code-block:: bash

      # Activate your ArcGIS Pro Python environment first
      pip install pyyaml boto3 keyring matplotlib

Environment Verification
------------------------

Before using the main workflow, verify your environment using the included environment checker:

1. **Add Environment Checker Toolbox:**

   - In ArcGIS Pro Catalog pane, right-click **Toolboxes**
   - Select **Add Toolbox**
   - Navigate to and select ``rmi_360_env_checker.pyt``

2. **Run Environment Check:**

   - Expand the **RMI 360 Environment Checker** toolbox
   - Run the **Check Required Python Packages** tool
   - Review the output to ensure all packages are installed

Installation Steps
------------------

1. **Clone the Repository:**

   .. code-block:: bash

      git clone https://github.com/RMI-Valuation/rmi-360-workflow-pyt.git
      cd rmi-360-workflow-pyt

2. **Setup Configuration:**

   .. code-block:: bash

      # Copy the sample config and customize it
      cp configs/config.sample.yaml configs/config.yaml

3. **Add to ArcGIS Pro:**

   - Open ArcGIS Pro and load a project (``.aprx``)
   - In the **Catalog** pane, right-click **Toolboxes** → **Add Toolbox**
   - Navigate to and select ``rmi_360_workflow.pyt``

4. **Verify Installation:**

   - Run the environment checker as described above
   - Ensure the **RMI 360 Workflow** toolbox appears in your Catalog pane
   - Verify tools are organized under **Setup**, **Individual Tools**, and **Orchestrator** groups

Troubleshooting
---------------

**Toolbox Warning Icon (❗)**
   If you see a warning icon when loading the toolbox:

   1. Remove the toolbox from ArcGIS Pro
   2. Re-add the toolbox - this usually resolves the issue

**Missing Python Packages**
   Use the environment checker tool to identify missing packages, then install them using the ArcGIS Pro Package Manager.

**Version Compatibility**
   Ensure you're using **v1.1.1** or later. Version v1.1.0 contained critical bugs that may render the workflow unusable.

Next Steps
----------

After installation, proceed to :doc:`configuration` to set up your project-specific settings.
