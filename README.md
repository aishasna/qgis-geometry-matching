**qgis-geometry-matching**

A custom QGIS Processing Algorithm in Python for automated cadastral data reconciliation and spatial relationship classification.

---

**Key Parameters**
* **Layer A & B**: The input polygon layers for comparison (e.g., base parcel layer vs. target tax layer).
* **Overlap Match Threshold**: The minimum intersection area percentage required to validate and classify a relationship (Default: `0.70` / 70%).

---

**Workflow Methodology**

The algorithm executes spatial processing in four streamlined stages:

1. **Spatial Indexing (R-Tree Architecture)**
   Utilizes QgsSpatialIndex to perform bounding-box intersection lookups, significantly enhancing computational performance compared to standard nested-loop processing.
2. **Dual-Perspective Ratio Calculation**
   Calculates the intersection percentage from both directions ($R_A$ and $R_B$). This dual-ratio approach is critical for distinguishing partial overlaps, splits, and merges.
3. **Topological Degree Resolution**
   Employs a dictionary-based tracking system to map relationship degrees between intersecting features. This accurately identifies complex connectivity (e.g., when a single polygon in Layer A correlates with multiple polygons in Layer B).
4. **Multi-Pass Classification Engine**
   * **Pass 1 (1:1 Match)**: Identifies clean 1:1 relationships for perfect or high-fidelity matches.
   * **Pass 2 (1:M Split / M:1 Merge)**: Classifies complex relationships based on area threshold clusters.
   * **Pass 3 (Need Review)**: Isolates "Need Review" features for low-overlap outliers or topologically invalid geometries.

---
**How to Use**
1. Copy the full script from `geometry-matching.py`.
2. In QGIS, open the **Processing Toolbox** (`Ctrl+Alt+T`).
3. Click the **Python icon** 🐍 -> **Create New Script from Template**.
4. Paste the code into the editor, click save, and the tool will instantly appear under your **Custom Scripts** menu.

---

**Commitment to Continuous Improvement**

As I continue to develop my skills in spatial data science, I am dedicated to continuous learning and technical refinement. I actively welcome feedback from the GIS community and domain experts to improve the robustness and efficiency of this algorithm. This repository represents a personal project that I plan to iterate upon as I sharpen my technical capabilities.

---
**Development & Academic Integrity**
* **Workflow & Logic**: The core conceptual architecture, spatial indexing strategy, and multi-pass classification logic were entirely designed and structured by the author.
* **Implementation**: Large Language Models (AI) were utilized strictly as technical coding assistants to accelerate the implementation of Python syntax, ensuring full compatibility with the native `QgsProcessingAlgorithm` framework.


