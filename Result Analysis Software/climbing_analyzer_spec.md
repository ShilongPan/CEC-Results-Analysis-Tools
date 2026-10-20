# Climbing Competition Results Analyzer — Specification Document

> **Audience:** Junior developer / coding agent  
> **Goal:** Build a portable cross-platform desktop app for interactive visualization of climbing competition CSV data.  
> **Deliverable:** A single Python script (`climbing_analyzer.py`) that can be run with `python climbing_analyzer.py` on Windows, macOS, or Linux.

---

## 1. Technology Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Language | Python 3.9+ | Widely available, great data viz ecosystem |
| GUI Framework | **PySide6** (LGPL, no licensing headaches) | Cross-platform, Qt-based, modern |
| Plotting | **matplotlib** (with `FigureCanvasQTAgg` from `matplotlib.backends.backend_qtagg`) | Native Qt integration, interactive zoom/pan out of the box |
| Data | **pandas** | CSV parsing, grouping, ranking |
| Packaging (optional) | **PyInstaller** | For distributing as a standalone `.exe` / `.app` / binary |

**Minimum dependencies** (install via `pip install -r requirements.txt`):
```
PySide6>=6.5
matplotlib>=3.7
pandas>=2.0
```

---

## 2. CSV Data Contract

The app reads any CSV with this **fixed column order**:

| Column index | Name | Type | Notes |
|-------------|------|------|-------|
| 0 | `name` | string | Athlete name (may appear in multiple rows) |
| 1 | `score` | float | Final score in the round (higher = better) |
| 2 | `category` | string | Competition category (e.g. `openmalefinal`) |
| 3+ | `pN_top`, `pN_zone` | int or empty | Attempts to top/zone problem N. Empty string if never attempted. |

**Key observations from sample data:**
- Problem count is **variable per category** (4, 8, 10, 21 in the sample). The app must **discover the number of problems dynamically** by scanning column headers.
- Empty cells mean the athlete did not attempt that problem (or no result was recorded). These should be excluded from box plot calculations and noted in the display.
- An athlete can appear in multiple categories (multiple rows with same name, different category).

---

## 3. Application Architecture

```
climbing_analyzer.py
├── DataModule
│   ├── load_csv(filepath) → DataFrame
│   ├── discover_problems(df) → list of problem indices
│   ├── get_categories(df) → list of unique categories
│   ├── get_athletes_in_category(df, category) → list of names
│   ├── get_athlete_data(df, category, name) → dict of problem stats
│   └── find_threshold_place(df, category, place) → score value (score at Nth place)
├── PlotModule
│   ├── draw_histogram(ax, scores, highlighted, colors, bin_width, threshold_score, threshold_place)
│   └── draw_boxplots(ax, df, category, problems, highlighted, colors, threshold_place)
└── GUI
    ├── MainWindow (QMainWindow)
    │   ├── Sidebar (QWidget with controls)
    │   │   ├── File loader (QPushButton → QFileDialog)
    │   │   ├── Category selector (QComboBox)
    │   │   ├── Athlete selector (QListWidget with checkboxes)
    │   │   ├── Color picker per athlete (QColorDialog triggered from QListWidget)
    │   │   ├── Histogram bin width slider (QSlider or QDoubleSpinBox)
    │   │   ├── Threshold place selector (QSpinBox, default=8)
    │   │   └── Reset / Clear buttons
    │   └── Plot Area (QTabWidget or split layout)
    │       ├── Tab 1: Histogram (matplotlib FigureCanvas)
    │       └── Tab 2: Box Plots (matplotlib FigureCanvas)
    └── event handlers (wire controls → redraw)
```

### File Structure

```
climbing_analyzer/
├── climbing_analyzer.py       # Main entry point (everything in one file for simplicity)
├── requirements.txt
├── README.md
└── spec/
    └── climbing_analyzer_spec.md  (this file)
```

> **Deliverable requirement:** The app should be a single runnable file if possible. If splitting is cleaner, keep it to no more than 3 files.

---

## 4. UI Layout & Controls

### 4.1 Overall Layout

```
┌──────────────────────────────────────────────────────────────────┐
│  [📂 Load CSV]  [Category: ▼ openmalefinal ▼]                  │
│                                                                  │
│  ┌──────────┐  ┌──────────────────────────────────────────────┐ │
│  │  SIDEBAR │  │              PLOT AREA                       │ │
│  │          │  │  ┌─────────────────┐  ┌──────────────────┐  │ │
│  │ ATHLETES │  │  │                 │  │                  │  │ │
│  │          │  │  │   HISTOGRAM     │  │   BOX PLOTS      │  │ │
│  │ [ ] Ath1 │  │  │   (zoom/pan)    │  │   (zoom/pan)     │  │ │
│  │ [ ] Ath2 │  │  │                 │  │                  │  │ │
│  │ [ ] Ath3 │  │  │                 │  │                  │  │ │
│  │          │  │  └─────────────────┘  └──────────────────┘  │ │
│  │ SETTINGS │  │                                              │ │
│  │          │  │                                              │ │
│  │ Bin: [1] │  │                                              │ │
│  │ Threshold│  │                                              │ │
│  │ Place: [8]│ │                                              │ │
│  │          │  │                                              │ │
│  │ [Clear]  │  │                                              │ │
│  └──────────┘  └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 Sidebar Controls

#### File Loader
- **Button:** "Load CSV" → opens `QFileDialog.getOpenFileName()` filtering for `*.csv`
- On load: populate category dropdown, clear all selections

#### Category Selector
- **Widget:** `QComboBox`
- Populated dynamically from CSV column 2 (category)
- Triggers: reload athlete list, redraw plots

#### Athlete Selector
- **Widget:** `QListWidget` in checkbox mode
- Populated from unique names in the selected category
- Each item has a **color indicator** (colored square or right-click → "Change Color")
- Clicking checkbox → toggles highlight for that athlete
- **Right-click** an athlete → `QColorDialog` to pick custom color (default: random distinct color from a palette)
- Default color palette (12 distinct, colorblind-safe colors):
  ```python
  DEFAULT_COLORS = [
      "#FF6B6B",  # red
      "#4ECDC4",  # teal
      "#45B7D1",  # blue
      "#96CEB4",  # green
      "#FFEAA7",  # yellow
      "#DDA0DD",  # plum
      "#98D8C8",  # mint
      "#F7DC6F",  # gold
      "#BB8FCE",  # purple
      "#85C1E9",  # light blue
      "#F0B27A",  # orange
      "#82E0AA",  # light green
  ]
  ```

#### Histogram Bin Width
- **Widget:** `QSlider` (range: 0.1 to 10.0, step 0.1) with a `QLabel` showing current value
- Default: 1.0
- Directly controls matplotlib histogram `bins` parameter (computed as `range / bin_width` or use `np.histogram_bin_edges`)

#### Threshold Place Selector
- **Widget:** `QSpinBox` (range: 1 to 50, step 1)
- Default: 8
- Label: "Threshold at place #"
- When value changes:
  1. Sort athletes in category by score descending
  2. Find the score at that rank position (1-indexed)
  3. Redraw plots with updated threshold line

#### Clear / Reset
- **Button:** "Clear Highlights" → unchecks all athletes, restores default colors
- **Button:** "Reset View" → resets histogram zoom/pan to full data range

---

## 5. Plot 1 — Score Histogram

### 5.1 Behavior

- **X-axis:** Final score (float, from CSV column 1)
- **Y-axis:** Count of athletes
- **Bins:** Determined by user-selected bin width
  - Compute as: `bin_count = ceil((max_score - min_score) / bin_width)`
  - Use `matplotlib.pyplot.hist()` with `bins=bin_count`
- **All athletes:** Drawn as a standard histogram bar fill (e.g., light gray or semi-transparent blue `alpha=0.5`)
- **Highlighted athletes:** Drawn as **vertical colored lines** at their exact score position, on top of the histogram
  - Line width: 3 pts
  - Line style: solid
  - Color: user-selected (or default palette)
  - If multiple athletes share the same score, lines overlap (acceptable)

### 5.2 Threshold Line

- **Purpose:** Show the score of whoever is in Nth place (default 8th)
- **Computation:**
  1. Get all scores in the selected category
  2. Sort descending
  3. Take the score at index `place - 1` (1-indexed)
  4. If `place > len(scores)`, show a warning and disable the line
- **Rendering:** Vertical line (`axvline`) at the threshold score
  - Color: dark red (`#E74C3C`)
  - Style: dashed (`--`)
  - Width: 2 pts
  - Label: `"8th place: {score:.1f}"` (dynamic)
- **Toggle:** Always visible when threshold place is valid (no toggle button needed — it's the default behavior)

### 5.3 Interactivity

- **Zoom/Pan:** Native matplotlib `NavigationToolbar2QT` embedded in the canvas
- **Reset:** Button restores original data limits
- **Legend:** Show athlete names as legend entries for highlighted lines (if ≤ 10 highlighted; hide if more to avoid clutter)

---

## 6. Plot 2 — Problem Attempt Box Plots

### 6.1 Layout & Scaling

- **X-axis:** Problem number (1, 2, 3, ... up to N problems, discovered dynamically)
- **Y-axis:** Number of attempts (integer, shared across all box plots)
- **Box plot width:** Constant for all problems (e.g., 0.6 on the x-axis scale)
- **Scaling:** Y-axis autoscales to fit all data, but the plot area width remains constant regardless of problem count
  - Use `figsize` that adapts to problem count: `width = max(8, problem_count * 1.2)`, `height = 6`
  - This ensures the plot stays readable whether there are 4 or 21 problems

### 6.2 Per-Problem Grouping

For each problem, display **two adjacent box plots**:

| Order | Type | Color |
|-------|------|-------|
| Left | Attempts to **zone** | **Orange** (`#FF8C00`) |
| Right | Attempts to **top** | **Blue** (`#4169E1`) |

This orange/blue scheme is intentional for colorblind accessibility.

### 6.3 Box Plot Details

For each box plot:
- **Data source:** All non-empty values for that problem's zone/top column across all athletes in the category
- **Whiskers:** Standard matplotlib boxplot (1.5×IQR)
- **Medians:** Shown as default line
- **Outliers:** Shown as default dots
- **Empty problem handling:** If all values for a problem are empty, show no box plot (or a dashed "no data" indicator)

### 6.4 Blank Value Annotation

- **Below each pair** of box plots, display the count of blank (empty) values:
  ```
  P1
   ┌──────┐
   │ zone │ top │
   └──────┴─────┘
    12 blank
  ```
- Implementation: Use `ax.text()` below each x-position with the blank count
  - Format: `"{blank_count} blank"` in small font (8pt)
  - Color: gray
  - Position: just below the x-axis labels, rotated 0 degrees
  - Only show if `blank_count > 0`

### 6.5 Highlighted Athlete Markers

- **Marker type:** Circular (`marker='o'`)
- **Marker size:** 6 pts (adjustable with `s` parameter)
- **Marker color:** Same as the athlete's selected highlight color
- **Y-position:** The athlete's actual attempt count for that problem
  - Only plot if the athlete has a non-empty value for that problem
- **X-position:** Centered on the problem's x-position
  - For zone: offset left by 0.15
  - For top: offset right by 0.15
  - (Adjust offsets based on box plot width to avoid overlap)
- **Multiple athletes jitter:** If **more than 2 athletes** are highlighted:
  - Apply random x-jitter to each athlete's marker within each problem group
  - Jitter range: ±0.1 (small enough to stay within the problem group, large enough to separate markers)
  - Use a fixed random seed so jitter is consistent across redraws
  - If ≤ 2 athletes highlighted: no jitter (markers are clearly visible without it)

### 6.6 Problem Labels

- X-axis labels: `P1`, `P2`, `P3`, ..., `P{N}`
- Bold, slightly larger font (10pt)
- If there are many problems (>15), rotate labels 45 degrees to avoid overlap

### 6.7 Interactivity

- **Zoom/Pan:** Native matplotlib toolbar
- **Hover tooltip (bonus):** Show athlete name + score on marker hover (use `matplotlib.widgets.Cursor` or `mplcursors`)

---

## 7. Data Processing Logic

### 7.1 Discover Problems

```python
def discover_problems(df):
    """Return list of (problem_number, top_col_name, zone_col_name) tuples."""
    problems = []
    for col in df.columns:
        if col.endswith('_top'):
            prob_num = int(col.replace('p', '').replace('_top', ''))
            problems.append((prob_num, col, f'p{prob_num}_zone'))
        elif col.endswith('_zone'):
            prob_num = int(col.replace('p', '').replace('_zone', ''))
            # Only add if the matching _top column exists
            if f'p{prob_num}_top' in df.columns:
                problems.append((prob_num, f'p{prob_num}_top', col))
    # Remove duplicates (each problem appears twice from top and zone)
    seen = set()
    unique = []
    for p in problems:
        if p[0] not in seen:
            seen.add(p[0])
            unique.append(p)
    return sorted(unique, key=lambda x: x[0])
```

### 7.2 Compute Threshold Score

```python
def get_threshold_score(df, category, place):
    """Get the score at the given rank position (1-indexed) in the category."""
    cat_scores = df[df['category'] == category]['score'].sort_values(ascending=False)
    if place <= len(cat_scores):
        return cat_scores.iloc[place - 1]
    return None  # Place exceeds number of athletes
```

### 7.3 Gather Box Plot Data

```python
def get_boxplot_data(df, category, problems):
    """Return dict: {prob_num: {'zone': [values], 'top': [values], 'zone_blank': N, 'top_blank': N}}"""
    data = {}
    cat_df = df[df['category'] == category]
    for prob_num, top_col, zone_col in problems:
        zone_vals = cat_df[zone_col].dropna()
        top_vals = cat_df[top_col].dropna()
        zone_blank = cat_df[zone_col].isna().sum()
        top_blank = cat_df[top_col].isna().sum()
        data[prob_num] = {
            'zone': zone_vals.astype(int).tolist(),
            'top': top_vals.astype(int).tolist(),
            'zone_blank': int(zone_blank),
            'top_blank': int(top_blank),
        }
    return data
```

---

## 8. Event Flow Summary

```
User loads CSV
    → Parse CSV with pandas
    → Discover categories → populate category combo box
    → Default to first category

User changes category
    → Filter data to category
    → Populate athlete list
    → Redraw both plots

User checks/unchecks athlete
    → Add/remove athlete from highlighted list with their color
    → Redraw both plots

User changes bin width
    → Update histogram bin count
    → Redraw histogram

User changes threshold place
    → Recompute threshold score
    → Redraw both plots (threshold line position changes)

User changes athlete color
    → Update athlete's color in highlighted list
    → Redraw both plots
```

---

## 9. Edge Cases & Error Handling

| Scenario | Handling |
|----------|----------|
| CSV file cannot be parsed | Show `QMessageBox.warning` with error details |
| CSV has wrong number of columns | Warn user: "Expected at least 3 columns (name, score, category)" |
| Category has fewer athletes than threshold place | Disable threshold line, show tooltip: "Only {N} athletes, threshold place {P} unavailable" |
| All values for a problem are empty | Skip box plot for that problem, show "no data" text |
| No athletes highlighted | Show warning: "Select at least one athlete to highlight" (don't crash) |
| User selects same color for multiple athletes | Allow it (user's choice), but warn if colors are too similar |
| Very large dataset (>10,000 rows) | Still functional, but note that box plots may be slow to render |
| Athlete name contains special characters | Use matplotlib's default text handling (should work fine) |

---

## 10. Non-Functional Requirements

- **Startup time:** < 2 seconds on a typical machine
- **Plot redraw time:** < 500ms for the sample dataset (~200 rows)
- **Memory:** Should handle datasets up to ~50,000 rows without issues
- **Cross-platform:** Tested on Windows, macOS (Intel + Apple Silicon), and Linux
- **No external API calls or internet dependency**
- **No persistent state** — app resets on close (no config file needed)

---

## 11. Implementation Steps (Suggested Order)

1. **Skeleton:** Set up PySide6 window with sidebar + two matplotlib canvases
2. **CSV loading:** Implement file dialog + pandas parsing + basic validation
3. **Category selector:** Populate dropdown from CSV data
4. **Athlete selector:** Populate checkbox list, implement color picking
5. **Histogram plot:** Render histogram with bin width control and threshold line
6. **Box plot:** Render box plots with problem discovery, blank annotations, and athlete markers
7. **Interactivity:** Wire up all controls to redraw handlers
8. **Polish:** Tooltips, error messages, legend, responsive layout, documentation

---

## 12. Testing Checklist

- [ ] Load the provided sample CSV (`pop_and_lock_9_results.csv`)
- [ ] Switch between categories (openmalefinal, openfemalefinal, openmalequali, youthbmale, etc.)
- [ ] Highlight single athlete → verify colored line on histogram and markers on box plots
- [ ] Highlight multiple athletes → verify jitter when > 2 athletes
- [ ] Change athlete color → verify update
- [ ] Adjust histogram bin width (0.1 to 10.0) → verify smooth update
- [ ] Change threshold place (1 to 50) → verify line moves or disappears appropriately
- [ ] Zoom and pan on both plots → verify correct behavior
- [ ] Test on all three platforms (Windows, macOS, Linux)
- [ ] Verify colorblind accessibility (orange zone / blue top distinction is clear)

---

## 13. Sample Code Snippets (Reference)

### Histogram with highlighted athletes
```python
import matplotlib.pyplot as plt
import numpy as np

fig, ax = plt.subplots()
all_scores = [69.7, 59.4, 44.3, 34.7, 29.8, 19.5, 19.2, 10.0, 84.5, 69.3, 54.2, 44.6, 44.6, 27.9, 25.0, 19.6]

# Histogram
bin_count = int(np.ceil((max(all_scores) - min(all_scores)) / bin_width))
ax.hist(all_scores, bins=bin_count, alpha=0.5, color='#4A90D9', label='All athletes')

# Threshold line
threshold_score = 44.6  # computed from data
ax.axvline(threshold_score, color='#E74C3C', linestyle='--', linewidth=2,
           label=f'{place}th place: {threshold_score:.1f}')

# Highlighted athletes
for name, score, color in highlighted:
    ax.axvline(score, color=color, linewidth=3, label=name)

ax.legend()
ax.set_xlabel('Final Score')
ax.set_ylabel('Count of Athletes')
ax.set_title('Score Distribution')
```

### Box plots with athlete markers
```python
fig, ax = plt.subplots()

# Prepare data for boxplot
zone_data = []
top_data = []
labels = []
x_positions = []
current_x = 0

for prob_num in sorted(problems):
    pdata = problem_data[prob_num]
    zone_vals = pdata['zone']
    top_vals = pdata['top']
    
    if zone_vals or top_vals:  # Only plot if there's data
        zone_data.append(zone_vals)
        top_data.append(top_vals)
        labels.append(f'P{prob_num}')
        x_positions.append(current_x)
        current_x += 1

# Plot box plots
if zone_data and top_data:
    all_data = zone_data + top_data
    all_labels = ['zone'] * len(zone_data) + ['top'] * len(top_data)
    positions = list(range(len(all_data)))
    
    bp = ax.boxplot(all_data, positions=positions, widths=0.6, patch_artist=True)
    
    for i, patch in enumerate(bp['boxes']):
        if i < len(zone_data):
            patch.set_facecolor('#FF8C00')  # Orange for zone
        else:
            patch.set_facecolor('#4169E1')  # Blue for top
        patch.set_alpha(0.7)
    
    # Color the medians
    for i, median in enumerate(bp['medians']):
        if i < len(zone_data):
            median.set_color('#E67E00')
        else:
            median.set_color('#2E5ACF')

# Add athlete markers
for prob_idx, prob_num in enumerate(sorted(problems)):
    pdata = problem_data[prob_num]
    for name, score, color in highlighted:
        if prob_num in athlete_problems[name]:
            val = athlete_problems[name][prob_num]
            x_offset = -0.15 if 'zone' else 0.15
            ax.scatter(positions[prob_idx] + x_offset, val,
                      color=color, s=60, zorder=5)

# Add blank annotations
for i, prob_num in enumerate(sorted(problems)):
    pdata = problem_data[prob_num]
    total_blank = pdata['zone_blank'] + pdata['top_blank']
    if total_blank > 0:
        ax.text(positions[i], -3, f'{total_blank} blank',
               ha='center', va='top', fontsize=8, color='gray')

ax.set_xticks(positions)
ax.set_xticklabels([f'P{p}' for p in sorted(problems)])
ax.set_xlabel('Problem')
ax.set_ylabel('Attempts')
ax.set_title('Attempts to Zone and Top by Problem')
```

---

## 14. Distribution

### Development
```bash
pip install -r requirements.txt
python climbing_analyzer.py
```

### Standalone executable (optional)
```bash
pip install pyinstaller
pyinstaller --onefile --windowed climbing_analyzer.py
# Output: dist/climbing_analyzer.exe (Windows) or climbing_analyzer (macOS/Linux)
```

---

*Document version: 1.0*  
*Date: 2026-10-20*  
*Author: Senior Analyst*
