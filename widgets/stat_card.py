"""
widgets/stat_card.py
~~~~~~~~~~~~~~~~~~~~
StatCard and chart_card widgets for KPI display.

This module provides:
- StatCard: A colored card widget for displaying KPI values
  with an icon, title, and numeric value
- chart_card: A helper function that wraps any widget in
  a titled white card frame

These widgets are used throughout the analysis panel to
display statistics and wrap chart widgets.

Color themes:
- blue: For general counts (tracks, frames)
- green: For positive metrics (entries, files)
- red: For negative metrics (exits)
- amber: For neutral metrics (net flow)
- purple: For additional metrics
- slate: For default/other metrics

Dependencies:
  - PyQt5.QtCore
  - PyQt5.QtGui
  - PyQt5.QtWidgets
"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget,
)

# Color theme definitions
# Each theme provides: (background, border, text, accent) colors
CARD_THEMES = {
    "blue":   ("#eff6ff", "#bfdbfe", "#1d4ed8", "#2563eb"),
    "green":  ("#f0fdf4", "#bbf7d0", "#15803d", "#16a34a"),
    "red":    ("#fef2f2", "#fecaca", "#b91c1c", "#dc2626"),
    "amber":  ("#fffbeb", "#fde68a", "#92400e", "#d97706"),
    "purple": ("#faf5ff", "#e9d5ff", "#6d28d9", "#7c3aed"),
    "slate":  ("#f8fafc", "#e2e8f0", "#334155", "#475569"),
}


class StatCard(QFrame):
    """
    Colored KPI card widget.
    
    Displays an icon, title, and numeric value with a color theme.
    Used for showing statistics like:
    - Number of files analyzed
    - Number of unique tracks
    - Entry/Exit counts
    - Net flow
    
    Attributes
    ----------
    _val : QLabel
        The label displaying the numeric value
    """

    def __init__(self, icon, title, value="—", variant="slate", parent=None):
        """
        Initialize a StatCard.
        
        Parameters
        ----------
        icon : str
            Emoji or symbol to display (e.g., "📂", "⬇")
        title : str
            Label title (e.g., "Files", "In", "Out")
        value : str
            Initial value to display (default "—")
        variant : str
            Color theme name from CARD_THEMES
        parent : QWidget, optional
            Parent widget
        """
        super().__init__(parent)
        
        # Get theme colors
        bg, border, txt, accent = CARD_THEMES.get(variant, CARD_THEMES["slate"])
        
        # Apply card styling
        self.setStyleSheet(
            f"QFrame{{background:{bg};border:1px solid {border};"
            f"border-radius:10px;}}"
        )
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(88)

        # Main layout
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 11, 14, 11)
        lay.setSpacing(3)

        # Top row: icon + title
        top = QHBoxLayout()
        
        # Icon label with colored background
        ico = QLabel(icon)
        ico.setStyleSheet(
            f"font-size:16px;background:{accent}22;"
            f"border-radius:6px;padding:4px 6px;color:{accent};"
        )
        ico.setFixedSize(32, 32)
        ico.setAlignment(Qt.AlignCenter)

        # Title label (uppercase, small, light)
        ttl = QLabel(title.upper())
        ttl.setStyleSheet(
            f"font-size:10px;font-weight:600;"
            f"letter-spacing:0.8px;color:{txt}88;"
        )
        
        top.addWidget(ico)
        top.addSpacing(6)
        top.addWidget(ttl)
        top.addStretch()

        # Value label (large, bold)
        self._val = QLabel(str(value))
        self._val.setStyleSheet(f"font-size:24px;font-weight:700;color:{txt};")
        
        lay.addLayout(top)
        lay.addWidget(self._val)

    def set_value(self, v):
        """
        Update the displayed value.
        
        Parameters
        ----------
        v : str or int
            New value to display
        """
        self._val.setText(str(v))


def chart_card(title: str, widget: QWidget) -> QFrame:
    """
    Wrap a widget in a titled white card frame.
    
    This helper function creates a QFrame with:
    - White background
    - Subtle border
    - Rounded corners
    - Optional title label at the top
    
    Parameters
    ----------
    title : str
        Title text to display above the widget
    widget : QWidget
        The widget to wrap (e.g., MiniBarChart, HeatmapWidget)
        
    Returns
    -------
    QFrame
        A frame widget containing the title and wrapped widget
    """
    # Create frame with card styling
    frame = QFrame()
    frame.setStyleSheet(
        "QFrame{background:#ffffff;border:1px solid #e5e7ef;border-radius:10px;}"
    )
    
    # Vertical layout
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(14, 12, 14, 12)
    
    # Add title if provided
    if title:
        lbl = QLabel(title)
        lbl.setStyleSheet(
            "font-size:12px;font-weight:600;color:#374151;border:none;"
        )
        lay.addWidget(lbl)
    
    # Add the widget
    lay.addWidget(widget)
    return frame
