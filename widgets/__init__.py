"""
widgets/__init__.py
~~~~~~~~~~~~~~~~~~~
Widgets package initialization.

This module exports the custom widget classes used throughout
the application for data visualization and UI components:

Chart widgets (from charts.py):
  - MiniBarChart: Vertical bar chart for distributions
  - MiniPieChart: Pie/donut chart for proportions
  - HeatmapWidget: 2D density heatmap
  - TrajectoryCanvas: Object trajectory visualization

UI widgets (from stat_card.py):
  - StatCard: KPI display card with icon, title, value
  - chart_card: Helper to wrap charts in titled frames
"""
from .charts import MiniBarChart, MiniPieChart, HeatmapWidget, TrajectoryCanvas
from .stat_card import StatCard, chart_card

__all__ = [
    "MiniBarChart", "MiniPieChart", "HeatmapWidget", "TrajectoryCanvas",
    "StatCard", "chart_card",
]