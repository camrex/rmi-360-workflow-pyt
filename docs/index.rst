RMI 360 Imaging Workflow Documentation
=======================================

.. image:: https://img.shields.io/badge/version-v1.1.1-blue
   :alt: Version

.. image:: https://img.shields.io/badge/python-3.11%2B-blue
   :alt: Python Version

.. image:: https://img.shields.io/badge/ArcGIS_Pro-3.4|3.5-green
   :alt: ArcGIS Pro Version

A modular workflow built with ArcGIS Python Toolbox for processing and deploying 360° corridor imagery.

Optimized for Mosaic 51 cameras, with planned support for Insta360. Includes tools for enhancement, OID creation, AWS publishing, and detailed reporting.

.. warning::
   **ArcGIS Pro Note:** When adding the Toolbox to ArcGIS Pro, you may see a warning icon (❗) upon loading. If this occurs, simply remove the Toolbox and add it again to resolve the issue.

.. note::
   The "Oriented Imagery" tools require **Standard or Advanced** licenses. All other functions are available with **Basic** or higher.

.. warning::
   Version **v1.1.0** contained critical bugs that may render the workflow unusable. Please use version **v1.1.1** or later, which resolves these issues.

Overview
--------

The RMI 360 Imaging Workflow provides comprehensive tools for:

- 🎞️ Processing captured imagery using Mosaic Processor (with support for MistikaVR or MosaicStitcher)
- 🧭 ArcGIS Oriented Imagery Dataset (OID) creation and enrichment
- 🏷️ EXIF metadata tagging
- 🛣️ Linear referencing support for image positioning
- 🧩 Custom attributing based on config-driven logic
- 🌍 Geocoding of image locations using spatial reference datasets
- 🗂️ File renaming and organization
- ☁️ AWS S3 upload with resumable transfer logic
- 📈 Lambda-based progress monitoring and status dashboard
- 📊 HTML & JSON reporting of process steps and status
- 🖼️ *Experimental:* Image enhancement (contrast, white balance, sharpening)

Key Features
------------

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Feature
     - Description
   * - Toolbox Structure
     - Built as an ArcGIS ``.pyt`` Toolbox + modular tool wrappers & utilities
   * - Config-Driven
     - YAML-based config with expression resolution and field registries
   * - AWS Integration
     - Upload to S3 with TransferManager + Lambda schedule tracking
   * - Resumable Transfers
     - Upload interruption protection + log recovery
   * - HTML & JSON Reporting
     - Auto-generated step summaries and final status reports
   * - Image Metadata Support
     - Auto tag EXIF metadata + rename by GPS, time, reel, frame, etc.

Quick Start
-----------

1. **Clone the Repository**

   .. code-block:: bash

      git clone https://github.com/RMI-Valuation/rmi-360-workflow-pyt.git
      cd rmi-360-workflow-pyt

2. **Setup Configuration**

   .. code-block:: bash

      # Copy and edit config
      cp configs/config.sample.yaml configs/config.yaml

3. **ArcGIS Pro Setup**

   - Open **ArcGIS Pro** and load a project (.aprx)
   - Add the environment checker toolbox: ``rmi_360_env_checker.pyt``
   - Run the **Check Required Python Packages** tool
   - Add the main toolbox: ``rmi_360_workflow.pyt``

Table of Contents
-----------------

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   user-guide/installation
   user-guide/configuration
   user-guide/quick-start
   user-guide/arcgis-setup

.. toctree::
   :maxdepth: 2
   :caption: Tools Documentation

   tools/overview
   tools/setup-tools
   tools/individual-tools
   tools/orchestrator

.. toctree::
   :maxdepth: 2
   :caption: Configuration

   config/overview
   config/project-settings
   config/aws-settings
   config/field-registry

.. toctree::
   :maxdepth: 2
   :caption: AWS Integration

   aws/setup-guide
   aws/s3-uploads
   aws/lambda-monitoring

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/tools
   api/utils
   api/managers
   api/validators

.. toctree::
   :maxdepth: 2
   :caption: Developer Guide

   developer/contributing
   developer/testing
   developer/architecture
   developer/changelog

Indices and Tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
