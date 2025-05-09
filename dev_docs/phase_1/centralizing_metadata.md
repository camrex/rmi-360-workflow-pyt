# 📍 Centralizing Metadata Management and Gathering

## **📖 Overview**
This task aims to centralize all metadata (latitude, longitude, elevation, timestamps, etc.) into a **SQLite database** for easy access, updating, and non-destructive edits.

![Version](https://img.shields.io/badge/effort-HIGH-red) ![Category](https://img.shields.io/badge/category-Foundational-blue)

**Objective**: Improve the workflow by capturing and storing metadata early in the image collection process, allowing users to make updates or reprocess images without starting from scratch.

---

## **🎯 Objectives**
- **Efficient Metadata Management**: Centralize all relevant metadata in a single database.
- **Non-Destructive Processing**: Enable updates to metadata without affecting the original images.
- **Reprocessing Capability**: Allow for reprocessing of images and metadata without unnecessary duplication of efforts.

---

## **🛠️ Action Items**
### 1. **Database Setup**
   - **Task**: Set up an **SQLite database** for metadata storage.
   - **Expected Outcome**: A single source of truth for all metadata.
   
   | Action | Description | Status |
   |--------|-------------|--------|
   | Database Setup | Implement SQLite database and schema | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |
   | Define Schema | Design the structure for storing metadata (lat/long, timestamps, etc.) | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |

### 2. **Metadata Capture**
   - **Task**: Implement metadata capture during the image collection process.
   - **Expected Outcome**: Ensure all necessary metadata is recorded alongside images during collection.
   
   | Action | Description | Status |
   |--------|-------------|--------|
   | Capture Coordinates | Store GPS coordinates (latitude and longitude) | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |
   | Capture Elevation | Store elevation data from the GPS device | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |
   | Capture Timestamp | Store timestamps for when each image is captured | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |

### 3. **Integrate Metadata into Processing Pipeline**
   - **Task**: Modify the existing pipeline to pull metadata from the database.
   - **Expected Outcome**: Ensure that metadata is applied consistently during image processing steps.
   
   | Action | Description | Status |
   |--------|-------------|--------|
   | Database Integration | Modify pipeline to retrieve metadata | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |
   | Apply Metadata to Images | Ensure that metadata is written to image files as EXIF data | ![Status](https://img.shields.io/badge/status-To--Do-lightgrey) |

---

## **📅 Timeline**

| Week | Task |
|------|------|
| **Week 1-2** | Set up database and schema, implement metadata capture. |
| **Week 3-4** | Integrate metadata into pipeline and test functionality. |

---

## **🎯 Milestones**

| Milestone | Expected Completion |
|-----------|---------------------|
| **M1**: Database schema defined | Week 2 |
| **M2**: Metadata capture implemented and validated | Week 3 |
| **M3**: Full integration with processing pipeline | Week 4 |

---

## **🧩 Dependencies**
- **Database schema** needs to be completed before metadata capture begins.
- Integration with **existing processing pipeline** is required before metadata can be fully applied to images.

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
- **Related GitHub Issue**: [#123](https://github.com/yourrepo/issues/123)
- **Pull Requests**: [PR #45](https://github.com/yourrepo/pull/45)

---
