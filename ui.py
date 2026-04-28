"""
ui.py
~~~~~
Main user interface shell for the YOLO Tracker application.

This module creates the top-level window with:
- A custom title bar with branding and status labels
- A QTabWidget containing the two main panels:
  1. LivePanel - real-time video detection and tracking
  2. LogAnalysisPanel - CSV log file analysis and visualization

The UI class serves as a thin wrapper that delegates most functionality
to the child panels. It provides the tab container and title bar,
while the panels handle their own content.

All public attributes previously on UI are now delegated to LivePanel,
but remain accessible through this class for backward compatibility
with the App class in app.py.

Dependencies:
    - PyQt5.QtCore
    - PyQt5.QtWidgets
    - panels.LivePanel
    - panels.LogAnalysisPanel
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QHBoxLayout, QFrame, QLabel, QScrollArea,
    QTabWidget, QVBoxLayout, QWidget,
)

# Import panel classes from the panels package
from panels import LivePanel, LogAnalysisPanel


class UI(QWidget):
    """
    Main window widget containing the tab interface.
    
    This is the top-level container that provides:
    - Window title and minimum size
    - Custom title bar with FPS and counter displays
    - Tab navigation between Live Detection and Log Analysis
    """
    
    # Class-level constant for stylesheet file path
    STYLE_QSS = "style.qss"

    @staticmethod
    def load_stylesheet(path: str) -> str:
        """
        Load the QSS (Qt Style Sheet) file contents.
        
        Parameters
        ----------
        path : str
            Relative or absolute path to the .qss file
            
        Returns
        -------
        str
            The contents of the stylesheet file
        """
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    def __init__(self):
        """
        Initialize the main UI window.
        
        Sets up:
        - Window title and size constraints
        - Stylesheet loading
        - Title bar construction
        - Tab widget with both panels
        """
        super().__init__()
        
        # Set window properties
        self.setWindowTitle("YOLO Detection + Tracking")
        self.setMinimumSize(980, 700)
        
        # Load and apply custom stylesheet
        self.setStyleSheet(self.load_stylesheet("style.qss"))
        
        # Build the UI components
        self._build_ui()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        """
        Build the complete UI layout.
        
        Creates:
        - Main vertical layout (root)
        - Title bar (fixed height 52px)
        - Tab widget with two tabs
        """
        # Root layout - no margins, no spacing
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Add title bar at the top
        root.addWidget(self._build_titlebar())

        # Create tab widget for panel switching
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)  # Cleaner tab appearance
        root.addWidget(self.tabs)

        # ── Tab 1: Live Detection ────────────────────────────────────────
        # The LivePanel handles real-time video processing
        self._live = LivePanel()
        self.tabs.addTab(self._live, "  Live Detection  ")

        # ── Tab 2: Log Analysis (scrollable) ─────────────────────────────
        # Wrap LogAnalysisPanel in a QScrollArea for when content exceeds view
        self.log_panel = LogAnalysisPanel()
        sc = QScrollArea()
        sc.setWidgetResizable(True)  # Allow panel to expand
        sc.setWidget(self.log_panel)
        # Transparent background for scroll area
        sc.setStyleSheet("QScrollArea{border:none;background:#f8f9fc;}")
        self.tabs.addTab(sc, "  Log Analysis  ")

    def _build_titlebar(self) -> QFrame:
        """
        Build the custom title bar with branding and status labels.
        
        Returns
        -------
        QFrame
            The configured title bar frame widget
        """
        # Create frame with fixed height
        tb = QFrame()
        tb.setObjectName("titlebar")
        tb.setFixedHeight(52)
        
        # Horizontal layout for title bar contents
        tbl = QHBoxLayout(tb)
        tbl.setContentsMargins(20, 0, 20, 0)

        # Brand label - app name and emoji
        brand = QLabel("🎯  YOLO Tracker")
        brand.setStyleSheet("font-size:15px;font-weight:700;color:#111827;")
        tbl.addWidget(brand)
        tbl.addStretch()  # Push labels to the right

        # FPS display label
        self.fps_label = QLabel("FPS: —")
        
        # Object counter label
        self.counter_label = QLabel("Objects: 0")
        
        # Apply common styling to status labels
        for lbl in (self.fps_label, self.counter_label):
            lbl.setStyleSheet(
                "color:#6b7280;font-size:12px;background:#f3f4f6;"
                "border:1px solid #e5e7ef;border-radius:5px;padding:3px 10px;"
            )
            tbl.addWidget(lbl)
            tbl.addSpacing(8)
        
        return tb

    # ------------------------------------------------------------------
    # Attribute delegation
    # ------------------------------------------------------------------

    def __getattr__(self, name: str):
        """
        Delegate attribute access to the LivePanel.
        
        This provides backward compatibility for code that expects
        attributes like self.video, self.select_btn, etc. to be directly
        on the App/UI class. Instead, these are retrieved from _live.
        
        Parameters
        ----------
        name : str
            The attribute name being accessed
            
        Returns
        -------
        Any
            The attribute value from LivePanel
            
        Raises
        ------
        AttributeError
            If the attribute doesn't exist on LivePanel
        """
        # Avoid infinite recursion during __init__
        if name.startswith("_"):
            raise AttributeError(name)
        
        # Get the LivePanel instance
        live = object.__getattribute__(self, "_live")
        
        # Delegate to LivePanel
        return getattr(live, name)
