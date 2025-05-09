# 💻 CLI and GUI Config Editors

## **📖 Overview**
This task aims to provide two methods for configuring the **RMI Mosaic 360 Toolbox**: a **CLI** for running pipelines independently of ArcGIS Pro, and a **GUI Config Editor** for a user-friendly interface to manage settings. This will enhance flexibility, allowing users to either automate processes from the command line or interact with an intuitive graphical interface.

![Version](https://img.shields.io/badge/effort-MEDIUM-orange) ![Category](https://img.shields.io/badge/category-Flexibility-yellow)

**Objective**: To allow users to configure and run the toolbox through both a command-line interface and a graphical user interface, providing options based on user preferences and workflow needs.

---

## **🎯 Objectives**
- **CLI Runner**: Create a **CLI runner** that allows users to execute image processing pipelines directly from the command line.
- **GUI Config Editor**: Develop an intuitive **GUI editor** to modify configuration files without manually editing YAML files.
- **Flexible User Interaction**: Offer both automation (CLI) and interaction (GUI) options to cater to different user preferences.

---

## **🛠️ Action Items**
### 1. **CLI Runner for Pipelines**
   - **Task**: Develop a **CLI runner** to enable users to run processing workflows via the command line, with options for specifying input, output, and other parameters.
   - **Expected Outcome**: Users can automate workflows using the CLI, making the toolbox more accessible for scripted or scheduled tasks.
   
   | Action | Description | Status |
   |--------|-------------|--------|
   | Define CLI Parameters | Define necessary parameters such as input, output, and config files | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |
   | Develop CLI Script | Create the Python script to process inputs and run workflows | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |
   | Integrate with Existing Tools | Ensure the CLI interacts smoothly with existing toolbox tools | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |

### 2. **GUI Config Editor**
   - **Task**: Create a **GUI config editor** (potentially using **Electron** or **Jupyter**) to allow users to modify configuration settings without directly editing the YAML files.
   - **Expected Outcome**: Provide a visual interface to manage configurations, reducing errors and improving user experience.
   
   | Action | Description | Status |
   |--------|-------------|--------|
   | Design Interface | Create wireframes or mockups for the GUI editor | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |
   | Develop GUI Application | Implement the actual editor using **Electron** or **Jupyter** | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |
   | Integrate Config Handling | Link the GUI with the RuntimeManager to apply changes to config | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |

### 3. **Ensure Compatibility and Flexibility**
   - **Task**: Ensure that both the CLI and GUI are compatible with the current config system and that changes in one are reflected in the other.
   - **Expected Outcome**: A seamless experience where users can switch between CLI and GUI without issues.
   
   | Action | Description | Status |
   |--------|-------------|--------|
   | Ensure CLI and GUI Sync | Ensure that changes made through CLI or GUI reflect in the config | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |
   | Test Config Updates | Verify that updates to configurations via either interface are successfully applied | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |

---

## **📅 Timeline**

| Week | Task |
|------|------|
| **Week 1-2** | Define parameters for CLI and design the initial GUI interface. |
| **Week 3** | Develop and integrate the CLI runner and GUI config editor. |
| **Week 4** | Test both interfaces for compatibility and usability. |

---

## **🎯 Milestones**

| Milestone | Expected Completion |
|-----------|---------------------|
| **M1**: CLI parameters defined | Week 2 |
| **M2**: GUI design completed | Week 2 |
| **M3**: CLI runner and GUI editor developed | Week 3 |
| **M4**: Testing and validation | Week 4 |

---

## **🧩 Dependencies**
- The **RuntimeManager** must be implemented before either the CLI or GUI can fetch and modify configuration values.
- The CLI and GUI need to be integrated with the existing configuration system.

---

## **👥 Team/Ownership**
- **Owner**: [Your Name]
- **Contributors**: [Team Members]

---

## **📊 Status/Progress**
- **Current Status**: ![Status](https://img.shields.io/badge/status-To--Do-lightgrey)
- **Last Update**: [Date of Last Update]

---

## **🔗 Links**
- **Related GitHub Issue**: [#126](https://github.com/yourrepo/issues/126)
- **Pull Requests**: [PR #48](https://github.com/yourrepo/pull/48)

---
