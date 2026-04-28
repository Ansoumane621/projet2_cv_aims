"""
panels/live_panel.py
~~~~~~~~~~~~~~~~~~~~
LivePanel — the "Live Detection" tab widget.

This panel provides the real-time video detection interface with:
- Video display area (left side)
- Control sidebar (right side) with:
  - Video source selection
  - Class filter checkboxes
  - Start/Stop/Pause controls
  - Live count displays (IN/OUT/NET)
  - Counting line position slider
  - Events log list

The panel exposes the same public attributes that App (main.py) expects,
allowing it to be used either as a standalone tab or accessed through
the parent UI class.

Public attributes:
  video              - QLabel for video display
  select_btn         - QPushButton for video file selection
  video_path_label   - QLabel showing selected video path
  start_btn          - QPushButton to start detection
  stop_btn           - QPushButton to stop detection
  pause_btn          - QPushButton to pause/resume
  class_select       - QComboBox for class filtering (hidden)
  line_slider        - QSlider for counting line position
  counter_label      - (delegated) Object count label
  fps_label          - (delegated) FPS display label
  list_widget        - QListWidget for events log

Public helper methods:
  get_live_allowed_classes() -> list
  get_line_y() -> int
  set_live_counts(enters, exits)

Dependencies:
  - PyQt5.QtCore
  - PyQt5.QtWidgets
  - constants.CLASS_PALETTE
  - widgets.StatCard
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QListWidget, QPushButton, QSlider,
    QVBoxLayout, QWidget,
)

from constants import CLASS_PALETTE
from widgets import StatCard


class LivePanel(QWidget):
    """
    Live Detection panel - real-time video analysis interface.
    
    This widget provides the left-right split layout with:
    - Left: Video display area (640x480 minimum)
    - Right: Control sidebar with all detection controls
    """

    def __init__(self, parent=None):
        """
        Initialize the LivePanel.
        
        Creates the horizontal layout with video display on the left
        and control sidebar on the right.
        """
        super().__init__(parent)
        
        # Main horizontal layout: video | controls
        ll = QHBoxLayout(self)
        ll.setContentsMargins(16, 16, 16, 16)  # 16px padding around panel
        ll.setSpacing(16)  # 16px gap between video and sidebar

        # ── Video display (left side) ──────────────────────────────────
        self.video = QLabel()
        self.video.setObjectName("video_label")
        self.video.setMinimumSize(640, 480)
        self.video.setAlignment(Qt.AlignCenter)
        self.video.setText("No Signal")  # Default text when no video
        self.video.setStyleSheet(
            "QLabel#video_label{background:#111827;border-radius:10px;"
            "color:#4b5563;font-size:16px;font-weight:600;}"
        )
        ll.addWidget(self.video, stretch=1)  # stretch=1 allows video to expand

        # ── Right sidebar (controls) ───────────────────────────────────
        rp = QVBoxLayout()
        rp.setSpacing(12)  # 12px vertical spacing between groups
        
        # Add each control group in order
        rp.addWidget(self._build_source_group())    # Video file selection
        rp.addWidget(self._build_class_filter())     # Class checkboxes
        rp.addWidget(self._build_controls())        # Start/Stop/Pause buttons
        rp.addWidget(self._build_live_counts())     # IN/OUT/NET displays
        rp.addWidget(self._build_line_slider())     # Counting line position
        rp.addWidget(self._build_events_log())      # Events list
        rp.addStretch()  # Push everything up, fill bottom with space
        
        ll.addLayout(rp)

    # ------------------------------------------------------------------
    # Group builders - each creates a QGroupBox with its contents
    # ------------------------------------------------------------------

    def _build_source_group(self) -> QGroupBox:
        """
        Build the "Video Source" group box.
        
        Contains:
        - Select button to open file dialog
        - Label showing selected video path
        """
        sg = QGroupBox("Video Source")
        sl = QVBoxLayout(sg); sl.setSpacing(8)
        
        # Video file selection button
        self.select_btn = QPushButton("📂  Select Video File")
        self.select_btn.setFixedHeight(34)
        
        # Label showing the selected video path
        self.video_path_label = QLabel("No video selected")
        self.video_path_label.setWordWrap(True)  # Wrap long paths
        self.video_path_label.setStyleSheet(
            "color:#6b7280;font-size:11px;background:#f9fafb;"
            "border:1px solid #e5e7ef;border-radius:6px;padding:6px 10px;"
        )
        
        sl.addWidget(self.select_btn)
        sl.addWidget(self.video_path_label)
        return sg

    def _build_class_filter(self) -> QGroupBox:
        """
        Build the "Class Filter" group box.
        
        Contains:
        - "All classes" tri-state checkbox
        - Individual class checkboxes (car, bus, truck, etc.)
        - Hidden QComboBox for backward compatibility
        """
        cg  = QGroupBox("Class Filter")
        cgv = QVBoxLayout(cg); cgv.setSpacing(6)

        # "All classes" tri-state checkbox
        # States: Checked (all on), Unchecked (all off), PartiallyChecked (mixed)
        self._live_all_cb = QCheckBox("All classes")
        self._live_all_cb.setChecked(True)
        self._live_all_cb.setTristate(True)  # Allow three states
        self._live_all_cb.setStyleSheet(
            "font-weight:600;color:#111827;"
            "QCheckBox::indicator:checked{background:#2563eb;border-color:#2563eb;}"
            "QCheckBox::indicator:indeterminate{background:#93c5fd;border-color:#2563eb;}"
        )
        cgv.addWidget(self._live_all_cb)

        # Horizontal separator line
        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#e5e7ef;"); cgv.addWidget(sep)

        # Grid of individual class checkboxes
        grid = QGridLayout(); grid.setSpacing(4)
        self._live_class_cbs: dict = {}  # Store checkbox references
        
        # Object classes to display
        for i, cls in enumerate(["car", "bus", "truck", "motorcycle", "bicycle", "person"]):
            # Get color from palette for this class
            col_hex = CLASS_PALETTE.get(cls, "#6b7280")
            
            # Create checkbox with class-specific color
            cb = QCheckBox(cls.capitalize()); cb.setChecked(True)
            cb.setStyleSheet(
                f"QCheckBox{{color:{col_hex};font-weight:500;}}"
                f"QCheckBox::indicator:checked{{background:{col_hex};"
                f"border-color:{col_hex};}}"
            )
            self._live_class_cbs[cls] = cb
            
            # Add to grid (2 columns)
            grid.addWidget(cb, i // 2, i % 2)
        cgv.addLayout(grid)

        # Hidden combo kept for internal compatibility with App
        # This allows App.class_select to work even though the real
        # filtering is done via checkboxes
        self.class_select = QComboBox()
        self.class_select.hide()

        # Connect checkbox signals to handlers
        self._live_all_cb.stateChanged.connect(self._on_live_all_toggled)
        for cb in self._live_class_cbs.values():
            cb.stateChanged.connect(self._on_live_class_toggled)
        
        return cg

    def _build_controls(self) -> QGroupBox:
        """
        Build the "Controls" group box.
        
        Contains:
        - Start button (row 1, spans 2 columns)
        - Pause button (row 2, col 0)
        - Stop button (row 2, col 1)
        """
        ctg = QGroupBox("Controls")
        ctr = QGridLayout(ctg); ctr.setSpacing(8)
        
        # Create control buttons
        self.start_btn = QPushButton("▶  Start")
        self.stop_btn  = QPushButton("■  Stop")
        self.pause_btn = QPushButton("⏸  Pause")
        
        # Set object names for styling
        self.start_btn.setObjectName("btn_start")
        self.stop_btn.setObjectName("btn_stop")
        self.pause_btn.setObjectName("btn_pause")
        
        # Standard button height
        for b in (self.start_btn, self.stop_btn, self.pause_btn):
            b.setFixedHeight(36)
        
        # Layout: Start spans full width, Pause/Stop side by side below
        ctr.addWidget(self.start_btn, 0, 0, 1, 2)  # row 0, col 0, span 2 columns
        ctr.addWidget(self.pause_btn, 1, 0)        # row 1, col 0
        ctr.addWidget(self.stop_btn,  1, 1)        # row 1, col 1
        return ctg

    def _build_live_counts(self) -> QGroupBox:
        """
        Build the "Live Counts" group box.
        
        Contains three StatCard widgets showing:
        - IN count (green) - objects moving downward across line
        - OUT count (red) - objects moving upward across line
        - NET count (amber) - IN minus OUT
        """
        stg = QGroupBox("Live Counts")
        stl = QHBoxLayout(stg); stl.setSpacing(8)
        
        # Create three stat cards
        self._live_in  = StatCard("⬇", "In",  "0", "green")
        self._live_out = StatCard("⬆", "Out", "0", "red")
        self._live_net = StatCard("≡", "Net", "—", "amber")
        
        for c in (self._live_in, self._live_out, self._live_net):
            stl.addWidget(c)
        return stg

    def _build_line_slider(self) -> QGroupBox:
        """
        Build the "Counting Line Position" group box.
        
        Contains:
        - Hint text explaining slider purpose
        - Current position label (e.g., "y = 240 px (50%)")
        - Horizontal slider (range 10-470)
        - Percentage markers below slider
        """
        grp = QGroupBox("Counting Line Position")
        lay = QVBoxLayout(grp); lay.setSpacing(6)

        # Top row: hint + position label
        top_row = QHBoxLayout()
        hint = QLabel("Set before Start — locked during playback")
        hint.setStyleSheet("color:#6b7280;font-size:11px;border:none;")
        
        self._line_y_label = QLabel("y = 240 px  (50%)")
        self._line_y_label.setStyleSheet(
            "color:#2563eb;font-size:11px;font-weight:600;border:none;")
        
        top_row.addWidget(hint); top_row.addStretch()
        top_row.addWidget(self._line_y_label)
        lay.addLayout(top_row)

        # Main slider control
        self.line_slider = QSlider(Qt.Horizontal)
        self.line_slider.setMinimum(10)    # Leave some margin
        self.line_slider.setMaximum(470)  # Leave some margin
        self.line_slider.setValue(240)    # Default to middle (50%)
        self.line_slider.setTickInterval(46)  # ~10% intervals
        self.line_slider.setTickPosition(QSlider.TicksBelow)
        
        # Custom slider styling
        self.line_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 5px; background: #e5e7ef; border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #2563eb; border: 2px solid #ffffff;
                width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
            }
            QSlider::handle:horizontal:hover { background: #1d4ed8; }
            QSlider::sub-page:horizontal { background: #2563eb; border-radius: 3px; }
        """)
        lay.addWidget(self.line_slider)

        # Bottom row: percentage markers
        pct_row = QHBoxLayout()
        for pct in ["Top (0%)", "25%", "Mid (50%)", "75%", "Bot (100%)"]:
            lbl = QLabel(pct)
            lbl.setStyleSheet("color:#9ca3af;font-size:9px;border:none;")
            lbl.setAlignment(Qt.AlignCenter)
            pct_row.addWidget(lbl)
        lay.addLayout(pct_row)

        # Connect slider to update handler
        self.line_slider.valueChanged.connect(self._on_line_slider_changed)
        return grp

    def _build_events_log(self) -> QGroupBox:
        """
        Build the "Events" group box.
        
        Contains a QListWidget that displays detection events
        as they occur during live processing.
        """
        lg  = QGroupBox("Events")
        lgl = QVBoxLayout(lg)
        
        self.list_widget = QListWidget()
        self.list_widget.setMaximumHeight(120)  # Limit height
        lgl.addWidget(self.list_widget)
        return lg

    # ------------------------------------------------------------------
    # Public helper methods (called by App)
    # ------------------------------------------------------------------

    def get_live_allowed_classes(self) -> list:
        """
        Get the list of currently checked object classes.
        
        Returns
        -------
        list
            List of class names that are currently checked/selected
            If none checked, returns all classes
        """
        checked = [cls for cls, cb in self._live_class_cbs.items() if cb.isChecked()]
        return checked if checked else list(self._live_class_cbs.keys())

    def get_line_y(self) -> int:
        """
        Get the current counting line Y position.
        
        Returns
        -------
        int
            The Y coordinate of the counting line (0 = top of frame)
        """
        return self.line_slider.value()

    def set_live_counts(self, enters: int, exits: int):
        """
        Update the live count displays.
        
        Parameters
        ----------
        enters : int
            Number of objects that entered (crossed downward)
        exits : int
            Number of objects that exited (crossed upward)
        """
        self._live_in.set_value(str(enters))
        self._live_out.set_value(str(exits))
        self._live_net.set_value(f"{enters - exits:+d}")

    # ------------------------------------------------------------------
    # Signal handlers (slots)
    # ------------------------------------------------------------------

    def _on_live_all_toggled(self, state):
        """
        Handle "All classes" checkbox state change.
        
        When the tri-state "All" checkbox is toggled, this syncs
        all individual class checkboxes to match.
        """
        checked = (state == Qt.Checked)
        for cb in self._live_class_cbs.values():
            # Block signals to prevent cascading updates
            cb.blockSignals(True); cb.setChecked(checked); cb.blockSignals(False)
        self._sync_class_select()

    def _on_live_class_toggled(self):
        """
        Handle individual class checkbox changes.
        
        Updates the tri-state "All" checkbox based on the state
        of individual class checkboxes:
        - All checked -> Checked
        - Some checked -> PartiallyChecked
        - None checked -> Unchecked
        """
        all_checked = all(cb.isChecked() for cb in self._live_class_cbs.values())
        any_checked = any(cb.isChecked() for cb in self._live_class_cbs.values())
        
        self._live_all_cb.blockSignals(True)
        if all_checked:
            self._live_all_cb.setCheckState(Qt.Checked)
        elif any_checked:
            self._live_all_cb.setCheckState(Qt.PartiallyChecked)
        else:
            self._live_all_cb.setCheckState(Qt.Unchecked)
        self._live_all_cb.blockSignals(False)
        
        self._sync_class_select()

    def _on_line_slider_changed(self, value: int):
        """
        Handle counting line slider value changes.
        
        Updates the position label to show current Y value and percentage.
        """
        # Calculate percentage (10-470 maps to 0-100%)
        pct = round((value - 10) / (470 - 10) * 100)
        self._line_y_label.setText(f"y = {value} px  ({pct}%)")

    def _sync_class_select(self):
        """
        Sync the hidden class_select combo with checkbox states.
        
        This maintains backward compatibility with code that uses
        class_select directly.
        """
        checked = [cls for cls, cb in self._live_class_cbs.items() if cb.isChecked()]
        if len(checked) in (0, len(self._live_class_cbs)):
            self.class_select.setCurrentText("ALL")
        elif len(checked) == 1:
            self.class_select.setCurrentText(checked[0])
        else:
            self.class_select.setCurrentText("ALL")
