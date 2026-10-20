#!/usr/bin/env python3
"""
Climbing Competition Results Analyzer
======================================
A portable cross-platform desktop app for interactive visualization
of climbing competition CSV data.

Usage:
    python climbing_analyzer.py

Dependencies:
    pip install PySide6 matplotlib pandas
"""

import sys
import math
import random
from pathlib import Path

import numpy as np
import pandas as pd
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QListWidget, QListWidgetItem, QPushButton, QSlider,
    QSpinBox, QLabel, QFileDialog, QMessageBox, QTabWidget,
    QColorDialog, QSplitter, QGroupBox, QFrame, QScrollArea,
    QDoubleSpinBox, QSizePolicy, QToolBar,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QFont, QAction, QIcon

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt import NavigationToolbar2QT
from matplotlib.figure import Figure

# ─── Constants ───────────────────────────────────────────────────────────────

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

HISTOGRAM_FILL_COLOR = "#4A90D9"
THRESHOLD_COLOR = "#E74C3C"
ZONE_COLOR = "#FF8C00"
TOP_COLOR = "#4169E1"
EMPTY_COLOR = "#CCCCCC"


# ─── Data Module ─────────────────────────────────────────────────────────────

class DataModule:
    """Handles CSV loading, parsing, and data queries."""

    def __init__(self):
        self.df = None
        self.categories = []
        self.problems = []
        self.current_category = None

    def load_csv(self, filepath: str) -> bool:
        """Load a CSV file. Returns True on success."""
        try:
            self.df = pd.read_csv(filepath)
            if self.df is None or self.df.empty:
                raise ValueError("CSV file is empty")
            if self.df.shape[1] < 3:
                raise ValueError(f"CSV has only {self.df.shape[1]} columns; expected at least 3 (name, score, category)")
            self.categories = self.df.iloc[:, 2].dropna().unique().tolist()
            self.categories.sort()
            self.problems = self._discover_problems()
            self.current_category = self.categories[0] if self.categories else None
            return True
        except Exception as e:
            raise e

    def _discover_problems(self) -> list:
        """Discover problem columns from DataFrame headers.

        Returns list of (problem_number, top_col_name, zone_col_name) tuples.
        """
        problems = {}
        for col in self.df.columns:
            if col.startswith('p') and ('_top' in col or '_zone' in col):
                try:
                    prob_num = int(col[1:].split('_')[0])
                    if prob_num not in problems:
                        problems[prob_num] = {}
                    if '_top' in col:
                        problems[prob_num]['top'] = col
                    elif '_zone' in col:
                        problems[prob_num]['zone'] = col
                except ValueError:
                    continue
        # Only include problems where both top and zone columns exist
        result = []
        for prob_num in sorted(problems.keys()):
            if 'top' in problems[prob_num] and 'zone' in problems[prob_num]:
                result.append((prob_num, problems[prob_num]['top'], problems[prob_num]['zone']))
        return result

    def get_categories(self) -> list:
        return self.categories

    def get_athletes_in_category(self, category: str) -> list:
        if self.df is None:
            return []
        cat_df = self.df[self.df['category'] == category]
        return cat_df['name'].dropna().unique().tolist()

    def get_athlete_data(self, category: str, name: str) -> dict:
        """Get attempt data for a specific athlete in a category.

        Returns dict: {prob_num: {'zone': value_or_None, 'top': value_or_None}}
        """
        if self.df is None:
            return {}
        cat_df = self.df[self.df['category'] == category]
        athlete_rows = cat_df[cat_df['name'] == name]
        if athlete_rows.empty:
            return {}
        row = athlete_rows.iloc[0]
        data = {}
        for prob_num, top_col, zone_col in self.problems:
            zone_val = row.get(zone_col, None)
            top_val = row.get(top_col, None)
            data[prob_num] = {
                'zone': int(zone_val) if pd.notna(zone_val) else None,
                'top': int(top_val) if pd.notna(top_val) else None,
            }
        return data

    def get_all_scores(self, category: str) -> list:
        """Get all scores in a category, sorted descending."""
        if self.df is None:
            return []
        cat_scores = self.df[self.df['category'] == category]['score'].dropna()
        return sorted(cat_scores.tolist(), reverse=True)

    def get_threshold_score(self, category: str, place: int) -> float:
        """Get the score at the given rank position (1-indexed) in the category."""
        scores = self.get_all_scores(category)
        if place <= len(scores):
            return scores[place - 1]
        return None

    def get_boxplot_data(self, category: str) -> dict:
        """Return dict: {prob_num: {'zone': [values], 'top': [values], 'zone_blank': N, 'top_blank': N}}"""
        if self.df is None:
            return {}
        cat_df = self.df[self.df['category'] == category]
        data = {}
        for prob_num, top_col, zone_col in self.problems:
            zone_vals = cat_df[zone_col].dropna()
            top_vals = cat_df[top_col].dropna()
            zone_blank = int(cat_df[zone_col].isna().sum())
            top_blank = int(cat_df[top_col].isna().sum())
            data[prob_num] = {
                'zone': zone_vals.astype(int).tolist(),
                'top': top_vals.astype(int).tolist(),
                'zone_blank': zone_blank,
                'top_blank': top_blank,
            }
        return data


# ─── Plot Module ─────────────────────────────────────────────────────────────

class HistogramCanvas(FigureCanvas):
    """Matplotlib canvas for the score histogram."""

    def __init__(self, parent=None):
        self.fig = Figure(figsize=(8, 5))
        super().__init__(self.fig)
        self.setParent(parent)
        self.ax = self.fig.subplots()
        self.navigation = NavigationToolbar2QT(self, parent)
        self.current_scores = []
        self.current_highlighted = []
        self.current_threshold = None
        self.current_threshold_place = None
        self.current_bin_width = 1.0

    def set_data(self, scores, highlighted, threshold_score, threshold_place, bin_width):
        """Update all plot data and redraw."""
        self.current_scores = scores
        self.current_highlighted = highlighted
        self.current_threshold = threshold_score
        self.current_threshold_place = threshold_place
        self.current_bin_width = bin_width
        self.draw()

    def draw(self):
        self.ax.clear()

        if not self.current_scores:
            self.ax.text(0.5, 0.5, 'No data to display',
                         ha='center', va='center', transform=self.ax.transAxes,
                         fontsize=14, color='gray')
            self.fig.canvas.draw()
            return

        scores = self.current_scores
        bin_count = max(1, int(math.ceil((max(scores) - min(scores)) / self.current_bin_width)))

        # Draw histogram
        self.ax.hist(scores, bins=bin_count, alpha=0.5, color=HISTOGRAM_FILL_COLOR,
                     label='All athletes')

        # Draw threshold line
        if self.current_threshold is not None:
            self.ax.axvline(self.current_threshold, color=THRESHOLD_COLOR, linestyle='--',
                            linewidth=2, label=f'{self.current_threshold_place}th place: {self.current_threshold:.1f}')

        # Draw highlighted athletes
        highlighted = self.current_highlighted
        if highlighted:
            for name, score, color in highlighted:
                self.ax.axvline(score, color=color, linewidth=3, label=name)

        # Legend
        if highlighted and len(highlighted) <= 10:
            self.ax.legend(loc='upper right', fontsize=8)
        elif highlighted:
            self.ax.legend(loc='upper right', fontsize=8, ncol=2)

        self.ax.set_xlabel('Final Score', fontsize=11)
        self.ax.set_ylabel('Count of Athletes', fontsize=11)
        self.ax.set_title('Score Distribution', fontsize=13, fontweight='bold')
        self.ax.grid(True, alpha=0.3)

        self.fig.canvas.draw()


class BoxPlotCanvas(FigureCanvas):
    """Matplotlib canvas for the problem attempt box plots."""

    def __init__(self, parent=None):
        self.fig = Figure(figsize=(8, 6))
        super().__init__(self.fig)
        self.setParent(parent)
        self.ax = self.fig.subplots()
        self.navigation = NavigationToolbar2QT(self, parent)
        self.current_boxplot_data = {}
        self.current_highlighted = []
        self.current_problems = []

    def set_data(self, boxplot_data, highlighted, problems):
        """Update all plot data and redraw."""
        self.current_boxplot_data = boxplot_data
        self.current_highlighted = highlighted
        self.current_problems = problems
        self.draw()

    def draw(self):
        self.ax.clear()

        if not self.current_problems:
            self.ax.text(0.5, 0.5, 'No problem data available',
                         ha='center', va='center', transform=self.ax.transAxes,
                         fontsize=14, color='gray')
            self.fig.canvas.draw()
            return

        problems = self.current_problems
        problem_data = self.current_boxplot_data
        highlighted = self.current_highlighted
        num_problems = len(problems)

        # Adapt figure width to problem count
        new_width = max(8, num_problems * 1.2)
        self.fig.set_size_inches(new_width, 6)

        # Prepare box plot data
        zone_data = []
        top_data = []
        labels = []
        x_positions = []
        current_x = 0

        for prob_num, top_col, zone_col in problems:
            pdata = problem_data.get(prob_num, {'zone': [], 'top': [], 'zone_blank': 0, 'top_blank': 0})
            zone_vals = pdata.get('zone', [])
            top_vals = pdata.get('top', [])

            if zone_vals or top_vals:
                zone_data.append(zone_vals)
                top_data.append(top_vals)
                labels.append(f'P{prob_num}')
                x_positions.append(current_x)
                current_x += 1

        if zone_data and top_data:
            all_data = zone_data + top_data
            positions = list(range(len(all_data)))

            bp = self.ax.boxplot(all_data, positions=positions, widths=0.6,
                                 patch_artist=True, showfliers=True, whiskersprops=dict(linewidth=1.5),
                                 medianprops=dict(linewidth=2))

            for i, patch in enumerate(bp['boxes']):
                if i < len(zone_data):
                    patch.set_facecolor(ZONE_COLOR)
                    patch.set_alpha(0.5)
                else:
                    patch.set_facecolor(TOP_COLOR)
                    patch.set_alpha(0.5)

            # Color the medians
            for i, median in enumerate(bp['medians']):
                if i < len(zone_data):
                    median.set_color('#E67E00')
                else:
                    median.set_color('#2E5ACF')

            # Add athlete markers
            num_highlighted = len(highlighted)
            if highlighted and (zone_data or top_data):
                rng = random.Random(42)

                for prob_idx, prob_num in enumerate(problems):
                    pdata = problem_data.get(prob_num, {})
                    for name, score, color in highlighted:
                        # Get athlete's attempt data
                        athlete_data = self.data.get_athlete_data(category, name)
                        attempt = athlete_data.get(prob_num, {})
                        zone_val = attempt.get('zone')
                        top_val = attempt.get('top')

                        # Jitter only when more than 2 athletes highlighted
                        jitter_x = 0
                        if num_highlighted > 2:
                            jitter_x = rng.uniform(-0.1, 0.1)

                        # Zone marker (left offset)
                        if zone_val is not None and zone_data:
                            x_pos = x_positions[prob_idx] - 0.15 + jitter_x
                            self.ax.scatter(x_pos, zone_val, color=color, s=60,
                                           zorder=5, marker='o', edgecolors='black',
                                           linewidths=0.5)

                        # Top marker (right offset)
                        if top_val is not None and top_data:
                            x_pos = x_positions[prob_idx] + 0.15 + jitter_x
                            self.ax.scatter(x_pos, top_val, color=color, s=60,
                                           zorder=5, marker='o', edgecolors='black',
                                           linewidths=0.5)

            # Add blank annotations
            for i, prob_num in enumerate(problems):
                pdata = problem_data.get(prob_num, {})
                zone_blank = pdata.get('zone_blank', 0)
                top_blank = pdata.get('top_blank', 0)
                total_blank = zone_blank + top_blank
                if total_blank > 0 and i < len(x_positions):
                    self.ax.text(x_positions[i], -3, f'{total_blank} blank',
                                 ha='center', va='top', fontsize=8, color='gray')

        self.ax.set_xticks(x_positions)
        self.ax.set_xticklabels(labels, fontsize=10, fontweight='bold')
        if num_problems > 15:
            self.ax.tick_params(axis='x', rotation=45)
        self.ax.set_xlabel('Problem', fontsize=11)
        self.ax.set_ylabel('Attempts', fontsize=11)
        self.ax.set_title('Attempts to Zone and Top by Problem', fontsize=13, fontweight='bold')
        self.ax.grid(True, alpha=0.3, axis='y')

        # Legend for box plot types
        from matplotlib.lines import Line2D
        legend_elements = [
            Line2D([0], [0], color=ZONE_COLOR, alpha=0.5, label='Zone'),
            Line2D([0], [0], color=TOP_COLOR, alpha=0.5, label='Top'),
        ]
        self.ax.legend(handles=legend_elements, loc='upper right', fontsize=9)

        self.fig.canvas.draw()


# ─── Athlete List Widget ─────────────────────────────────────────────────────

class AthleteListItem(QListWidgetItem):
    """Custom list item that stores athlete metadata."""
    def __init__(self, name, color, parent=None):
        super().__init__(name, parent)
        self.setForeground(QColor(color))
        self._color = color
        self._name = name
        self.setFlags(self.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        self.setCheckState(Qt.CheckState.Unchecked)

    @property
    def color(self):
        return self._color

    @color.setter
    def color(self, value):
        self._color = value
        self.setForeground(QColor(value))


# ─── Main Window ─────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.data = DataModule()
        self.highlighted = {}  # name -> (score, color)
        self.athlete_colors = {}  # name -> color
        self.color_index = 0
        self.current_bin_width = 1.0
        self.threshold_place = 8
        self.athlete_items = {}  # name -> AthleteListItem

        self._init_ui()
        self._apply_style()

    def _apply_style(self):
        """Apply a clean, modern stylesheet."""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #F5F5F5;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #DDDDDD;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 10px;
                background-color: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QPushButton {
                background-color: #4A90D9;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #357ABD;
            }
            QPushButton:pressed {
                background-color: #2C6AAF;
            }
            QPushButton#clearBtn {
                background-color: #E74C3C;
            }
            QPushButton#clearBtn:hover {
                background-color: #C0392B;
            }
            QPushButton#resetBtn {
                background-color: #95A5A6;
            }
            QPushButton#resetBtn:hover {
                background-color: #7F8C8D;
            }
            QComboBox {
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                padding: 5px 10px;
                background-color: white;
                font-size: 12px;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 10px;
            }
            QListWidget {
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                background-color: white;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 4px 8px;
                border-bottom: 1px solid #EEEEEE;
            }
            QListWidget::item:hover {
                background-color: #F0F0F0;
            }
            QListWidget::item:selected {
                background-color: #D6EAF8;
            }
            QSlider::groove:horizontal {
                border: 1px solid #CCCCCC;
                height: 8px;
                background: #EEEEEE;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #4A90D9;
                border: 1px solid #357ABD;
                width: 18px;
                height: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #357ABD;
            }
            QSpinBox, QDoubleSpinBox {
                border: 1px solid #CCCCCC;
                border-radius: 4px;
                padding: 4px 8px;
                background-color: white;
                font-size: 12px;
            }
            QLabel {
                font-size: 12px;
                color: #333333;
            }
            QTabWidget::pane {
                border: 1px solid #DDDDDD;
                border-radius: 6px;
                background-color: white;
            }
            QTabBar::tab {
                background-color: #EEEEEE;
                border: 1px solid #DDDDDD;
                border-bottom: none;
                padding: 8px 16px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: white;
                border-bottom: none;
            }
            QTabBar::tab:hover:!selected {
                background-color: #F0F0F0;
            }
        """)

    def _init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle('Climbing Competition Results Analyzer')
        self.resize(1200, 800)

        # ── Central widget ──
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # ── Top toolbar ──
        toolbar = QHBoxLayout()

        self.load_btn = QPushButton('📂 Load CSV')
        self.load_btn.setObjectName('loadBtn')
        self.load_btn.clicked.connect(self._load_csv)
        toolbar.addWidget(self.load_btn)

        toolbar.addSpacing(20)

        toolbar.addWidget(QLabel('Category:'))
        self.category_combo = QComboBox()
        self.category_combo.currentTextChanged.connect(self._on_category_changed)
        toolbar.addWidget(self.category_combo)

        toolbar.addStretch()

        main_layout.addLayout(toolbar)

        # ── Main content split ──
        content_splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Sidebar ──
        sidebar = QWidget()
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(8)

        # Athletes group
        athletes_group = QGroupBox('Athletes')
        athletes_layout = QVBoxLayout(athletes_group)

        self.athlete_list = QListWidget()
        self.athlete_list.setMaximumHeight(280)
        self.athlete_list.itemClicked.connect(self._on_athlete_toggled)
        self.athlete_list.customContextMenuRequested.connect(self._on_athlete_context_menu)
        athletes_layout.addWidget(self.athlete_list)

        sidebar_layout.addWidget(athletes_group)

        # Settings group
        settings_group = QGroupBox('Settings')
        settings_layout = QVBoxLayout(settings_group)

        # Bin width
        bin_layout = QHBoxLayout()
        bin_layout.addWidget(QLabel('Bin width:'))
        self.bin_slider = QSlider(Qt.Orientation.Horizontal)
        self.bin_slider.setRange(1, 100)  # 0.1 to 10.0 scaled by 10
        self.bin_slider.setValue(10)  # 1.0
        self.bin_slider.valueChanged.connect(self._on_bin_width_changed)
        self.bin_label = QLabel('1.0')
        bin_layout.addWidget(self.bin_slider)
        bin_layout.addWidget(self.bin_label)
        settings_layout.addLayout(bin_layout)

        # Threshold place
        thresh_layout = QHBoxLayout()
        thresh_layout.addWidget(QLabel('Threshold at place:'))
        self.threshold_spin = QSpinBox()
        self.threshold_spin.setRange(1, 100)
        self.threshold_spin.setValue(8)
        self.threshold_spin.valueChanged.connect(self._on_threshold_changed)
        thresh_layout.addWidget(self.threshold_spin)
        settings_layout.addLayout(thresh_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        self.clear_btn = QPushButton('Clear Highlights')
        self.clear_btn.setObjectName('clearBtn')
        self.clear_btn.clicked.connect(self._clear_highlights)
        btn_layout.addWidget(self.clear_btn)

        self.reset_btn = QPushButton('Reset View')
        self.reset_btn.setObjectName('resetBtn')
        self.reset_btn.clicked.connect(self._reset_view)
        btn_layout.addWidget(self.reset_btn)
        settings_layout.addLayout(btn_layout)

        sidebar_layout.addWidget(settings_group)
        sidebar_layout.addStretch()

        sidebar.setLayout(sidebar_layout)
        content_splitter.addWidget(sidebar)

        # ── Plot area ──
        plot_area = QTabWidget()

        # Histogram tab
        hist_widget = QWidget()
        hist_layout = QVBoxLayout(hist_widget)
        hist_layout.setContentsMargins(0, 0, 0, 0)
        hist_layout.setSpacing(0)

        self.hist_canvas = HistogramCanvas(hist_widget)
        hist_layout.addWidget(self.hist_canvas.navigation)
        hist_layout.addWidget(self.hist_canvas)
        plot_area.addTab(hist_widget, '📊 Score Histogram')

        # Box plots tab
        box_widget = QWidget()
        box_layout = QVBoxLayout(box_widget)
        box_layout.setContentsMargins(0, 0, 0, 0)
        box_layout.setSpacing(0)

        self.box_canvas = BoxPlotCanvas(box_widget)
        box_layout.addWidget(self.box_canvas.navigation)
        box_layout.addWidget(self.box_canvas)
        plot_area.addTab(box_widget, '📦 Problem Box Plots')

        content_splitter.addWidget(plot_area)

        # Set splitter proportions
        content_splitter.setSizes([250, 950])
        sidebar.setFixedWidth(280)

        main_layout.addWidget(content_splitter)

        # ── Status bar ──
        self.statusBar().showMessage('Load a CSV file to get started')

    def _load_csv(self):
        """Open file dialog and load CSV."""
        filepath, _ = QFileDialog.getOpenFileName(
            self, 'Load CSV File', '', 'CSV Files (*.csv);;All Files (*)'
        )
        if not filepath:
            return

        try:
            self.data.load_csv(filepath)
        except ValueError as e:
            QMessageBox.warning(self, 'CSV Error', str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, 'Error', f'Failed to load CSV:\n{str(e)}')
            return

        # Populate categories
        self.category_combo.clear()
        self.category_combo.addItems(self.data.get_categories())

        # Reset state
        self.highlighted.clear()
        self.athlete_items.clear()
        self.color_index = 0

        # Load first category
        self._on_category_changed(self.category_combo.currentText())

        self.statusBar().showMessage(f'Loaded: {Path(filepath).name} — {len(self.data.categories)} categories, {len(self.data.df)} rows')

    def _on_category_changed(self, category):
        """Handle category selection change."""
        if not category or self.data.df is None:
            return

        self.data.current_category = category
        self.highlighted.clear()
        self.athlete_items.clear()
        self.color_index = 0

        # Populate athlete list
        self.athlete_list.clear()
        athletes = self.data.get_athletes_in_category(category)
        for name in athletes:
            color = self._get_next_color()
            item = AthleteListItem(name, color, self.athlete_list)
            self.athlete_items[name] = item

        self._redraw_plots()

    def _get_next_color(self):
        """Get the next color from the default palette, cycling through."""
        color = DEFAULT_COLORS[self.color_index % len(DEFAULT_COLORS)]
        self.color_index += 1
        return color

    def _on_athlete_toggled(self, item: QListWidgetItem):
        """Handle athlete checkbox toggle."""
        name = item.text()
        if item.checkState() == Qt.CheckState.Checked:
            self.highlighted[name] = (None, item.color)
        else:
            self.highlighted.pop(name, None)
        self._redraw_plots()

    def _on_athlete_context_menu(self, pos):
        """Handle right-click context menu on athlete list."""
        item = self.athlete_list.itemAt(pos)
        if not item:
            return

        menu = self.athlete_list.createStandardContextMenu()
        menu.addSeparator()

        change_color_action = QAction('Change Color', self.athlete_list)
        change_color_action.triggered.connect(lambda: self._change_athlete_color(item))
        menu.addAction(change_color_action)

        reset_color_action = QAction('Reset to Default Color', self.athlete_list)
        reset_color_action.triggered.connect(lambda: self._reset_athlete_color(item))
        menu.addAction(reset_color_action)

        menu.exec(self.athlete_list.mapToGlobal(pos))

    def _change_athlete_color(self, item: QListWidgetItem):
        """Open color picker for an athlete."""
        current = QColor(item.color)
        color = QColorDialog.getColor(current, self, f'Choose color for {item.text()}')
        if color.isValid():
            item.color = color.name()
            self._redraw_plots()

    def _reset_athlete_color(self, item: QListWidgetItem):
        """Reset athlete color to the next palette color."""
        name = item.text()
        color = self._get_next_color()
        item.color = color
        self._redraw_plots()

    def _on_bin_width_changed(self, value):
        """Handle histogram bin width slider change."""
        self.current_bin_width = value / 10.0
        self.bin_label.setText(f'{self.current_bin_width:.1f}')
        self._redraw_plots()

    def _on_threshold_changed(self, value):
        """Handle threshold place selector change."""
        self.threshold_place = value
        self._redraw_plots()

    def _clear_highlights(self):
        """Uncheck all athletes and restore default colors."""
        self.highlighted.clear()
        for item in self.athlete_items.values():
            item.setCheckState(Qt.CheckState.Unchecked)
        self._redraw_plots()

    def _reset_view(self):
        """Reset zoom/pan on both plots."""
        self.hist_canvas.ax.relim()
        self.hist_canvas.ax.autoscale_view()
        self.hist_canvas.fig.canvas.draw()

        self.box_canvas.ax.relim()
        self.box_canvas.ax.autoscale_view()
        self.box_canvas.fig.canvas.draw()

    def _redraw_plots(self):
        """Redraw both plots with current data."""
        if self.data.df is None or self.data.current_category is None:
            return

        category = self.data.current_category
        scores = self.data.get_all_scores(category)

        # Build highlighted list
        highlighted_list = []
        for name, (score, color) in self.highlighted.items():
            if score is None:
                # Look up score from data
                cat_df = self.data.df[self.data.df['category'] == category]
                athlete_rows = cat_df[cat_df['name'] == name]
                if not athlete_rows.empty:
                    score = float(athlete_rows.iloc[0]['score'])
                else:
                    continue
            highlighted_list.append((name, score, color))

        # Threshold
        threshold_score = self.data.get_threshold_score(category, self.threshold_place)
        if threshold_score is not None:
            threshold_score = float(threshold_score)

        # Histogram
        self.hist_canvas.set_data(
            scores, highlighted_list, threshold_score,
            self.threshold_place, self.current_bin_width
        )

        # Box plots
        boxplot_data = self.data.get_boxplot_data(category)
        self.box_canvas.set_data(boxplot_data, highlighted_list, self.data.problems)

        # Update status
        n_highlighted = len(highlighted_list)
        if n_highlighted == 0:
            self.statusBar().showMessage(f'Showing {len(scores)} athletes in {category}. Select athletes to highlight.')
        else:
            self.statusBar().showMessage(f'Showing {len(scores)} athletes in {category}. Highlighted: {n_highlighted}')


# ─── Entry Point ─────────────────────────────────────────────────────────────

def main():
    """Entry point."""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # Cross-platform consistent look
    app.setApplicationName('Climbing Analyzer')
    app.setApplicationVersion('1.0')

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
