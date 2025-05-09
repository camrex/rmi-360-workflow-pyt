# 💻 Optional CLI Runner for Pipelines

## **📖 Overview**
**Objective**: Provide an **optional CLI runner** for executing image processing workflows from the command line. This feature will enhance automation and flexibility, allowing users to trigger the processing pipeline without relying on ArcGIS Pro, making it suitable for users who prefer a command-line interface (CLI) or automated batch processing.

![Version](https://img.shields.io/badge/effort-MEDIUM-orange) ![Category](https://img.shields.io/badge/category-Flexibility-yellow)

**Objective**: To implement a CLI interface that allows users to trigger the image processing pipeline with configurable options, such as input/output directories, processing steps, and other parameters.

---

## **🎯 Objectives**
- **Objective 1**: Develop a command-line interface that can trigger the entire processing pipeline.
- **Objective 2**: Allow users to specify input and output directories, processing parameters, and other configuration settings directly from the CLI.
- **Objective 3**: Ensure the CLI is compatible with the existing pipeline and can integrate seamlessly with other tools and workflows.

---

## **🛠️ Action Items**
### 1. **Define CLI Parameters (Input/Output, Options)**
   - **Task**: Define the command-line parameters needed to run the pipeline, including input/output directories, processing options (e.g., metadata application, stitching), and any other configurable settings.
   - **Expected Outcome**: Clear set of CLI parameters that allow users to customize their workflow from the command line.

| Action | Description | Status |
|--------|-------------|--------|
| Define Required Parameters | List required parameters (e.g., input directory, output directory) | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |
| Define Optional Parameters | Identify optional parameters for customization (e.g., processing steps, metadata) | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |
| Document Parameters | Create a help message to document available parameters and usage | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |

### 2. **Develop CLI Script to Trigger Pipeline**
   - **Task**: Develop the Python script that will handle the CLI input, trigger the image processing pipeline, and pass the necessary parameters.
   - **Expected Outcome**: A functional CLI script that can trigger the pipeline and execute the defined processing steps based on user inputs.
   
| Action | Description | Status |
|--------|-------------|--------|
| Implement CLI Script | Write the Python script that accepts CLI arguments and runs the processing pipeline | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |
| Integrate with Existing Tools | Ensure the CLI integrates with the existing image processing pipeline | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |
| Handle Input Validation | Add checks for required parameters and validate input files/directories | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |

### 3. **Allow Customization of Processing Steps**
   - **Task**: Enable users to specify which processing steps they want to run (e.g., metadata application, stitching, etc.) from the command line.
   - **Expected Outcome**: Flexibility for users to choose specific steps to execute without running the entire pipeline.
   
| Action | Description | Status |
|--------|-------------|--------|
| Define Processing Steps | List all available processing steps (e.g., metadata, stitching) | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |
| Implement Step Selection | Allow users to specify which steps to run via the CLI | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |
| Test Step Execution | Ensure that only selected steps are executed when triggered via CLI | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |

### 4. **Test CLI Functionality**
   - **Task**: Thoroughly test the CLI functionality with different parameters and processing scenarios to ensure it works as expected.
   - **Expected Outcome**: A fully functional CLI runner that allows users to execute the image processing pipeline with the correct parameters.
   
| Action | Description | Status |
|--------|-------------|--------|
| Test CLI with Sample Data | Run tests on sample images to ensure that the CLI triggers the pipeline correctly | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |
| Validate Input/Output | Ensure that input and output directories are correctly specified and used | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |
| Check Step Selection | Validate that the selected processing steps are executed correctly | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |

---

## **📅 Timeline**

| Week | Task |
|------|------|
| **Week 1** | Define CLI parameters and required input/output options. |
| **Week 2** | Develop the core CLI script and integrate with existing pipeline. |
| **Week 3** | Implement processing step selection and customization. |
| **Week 4** | Test CLI functionality and ensure everything works as expected. |

---

## **🎯 Milestones**

| Milestone | Expected Completion |
|-----------|---------------------|
| **M1**: Define CLI parameters and document usage | Week 1 |
| **M2**: Implement and integrate CLI script with processing pipeline | Week 2 |
| **M3**: Allow customization of processing steps | Week 3 |
| **M4**: Complete testing and validation of CLI functionality | Week 4 |

---

## **🧩 Dependencies**
- **Existing Processing Pipeline**: The CLI script must integrate with the current pipeline to trigger image processing steps.
- **Configuration System**: The CLI should pull settings and parameters from the existing configuration system for consistency.

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
- **Related GitHub Issue**: [#137](https://github.com/yourrepo/issues/137)
- **Pull Requests**: [PR #59](https://github.com/yourrepo/pull/59)
