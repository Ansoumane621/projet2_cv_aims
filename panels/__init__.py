"""
panels/__init__.py
~~~~~~~~~~~~~~~~~~
Panels package initialization.

This module exports the main panel classes used in the application:
- LivePanel: Real-time video analysis panel for YOLO detection
- LogAnalysisPanel: Historical log data analysis panel for CSV files

Usage:
    from panels import LivePanel, LogAnalysisPanel

The panels package contains the two main tab interfaces:
- live_panel.py: Live detection with video playback
- analysis_panel.py: CSV log analysis with charts and tables
"""
from .live_panel import LivePanel
from .analysis_panel import LogAnalysisPanel

# Public API - these classes are imported by ui.py and app.py
__all__ = ["LivePanel", "LogAnalysisPanel"]