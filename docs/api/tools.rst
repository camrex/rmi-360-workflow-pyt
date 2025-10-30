Tools API Reference
===================

This section documents the ArcGIS Python Toolbox tools that provide the user interface for the RMI 360 Workflow.

Overview
--------

The tools are organized into three main categories:

- **Setup Tools**: Configuration and environment preparation
- **Individual Tools**: Standalone processing steps
- **Orchestrator**: Complete workflow automation

Setup Tools
-----------

.. automodule:: tools.create_oid_template_tool
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: tools.set_aws_keyring_tool
   :members:
   :undoc-members:
   :show-inheritance:

Individual Processing Tools
---------------------------

Mosaic Processor
^^^^^^^^^^^^^^^^

.. automodule:: tools.run_mosaic_processor_tool
   :members:
   :undoc-members:
   :show-inheritance:

Image Processing
^^^^^^^^^^^^^^^^

.. automodule:: tools.rename_and_tag_tool
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: tools.enhance_images_tool
   :members:
   :undoc-members:
   :show-inheritance:

GPS and Location Processing
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: tools.smooth_gps_noise_tool
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: tools.geocode_images_tool
   :members:
   :undoc-members:
   :show-inheritance:

OID Creation and Management
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: tools.create_oid_tool
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: tools.add_images_to_oid_tool
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: tools.build_oid_footprints_tool
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: tools.update_linear_and_custom_tool
   :members:
   :undoc-members:
   :show-inheritance:

Publishing and Reporting
^^^^^^^^^^^^^^^^^^^^^^^^

.. automodule:: tools.generate_oid_service_tool
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: tools.copy_to_aws_tool
   :members:
   :undoc-members:
   :show-inheritance:

.. automodule:: tools.generate_report_tool
   :members:
   :undoc-members:
   :show-inheritance:

Orchestrator
------------

.. automodule:: tools.process_360_orchestrator
   :members:
   :undoc-members:
   :show-inheritance:
