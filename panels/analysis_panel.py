"""
panels/analysis_panel.py
~~~~~~~~~~~~~~~~~~~~~~~~
LogAnalysisPanel — the "Log Analysis" tab.

This panel provides CSV log file analysis and visualization:
- File import (single files or entire folders)
- CSV validation and filtering
- Statistical summary cards
- Multiple chart types (bar, pie, heatmap, trajectory)
- Data table with export capability

The panel reads detection logs produced by the live detection
session and provides interactive analysis tools.

Features:
- Multi-file CSV import with validation
- Class-based filtering
- 6 stat cards: Files, Tracks, Frames, Entries, Exits, Net Flow
- 6 charts: Class Distribution, Traffic Mix, Direction Split,
  Position Heatmap, Trajectory Map, Avg Confidence
- Data table with up to 10,000 rows
- CSV export of filtered data

Dependencies:
  - PyQt5.QtCore, PyQt5.QtGui, PyQt5.QtWidgets
  - csv, glob, os modules
  - collections.Counter, collections.defaultdict
  - constants (CLASS_PALETTE, EXPECTED_COLUMNS, etc.)
  - widgets (MiniBarChart, MiniPieChart, HeatmapWidget, etc.)
"""
import csv
import glob
import os
from collections import Counter, defaultdict

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView, QFileDialog, QFrame, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QListWidget,
    QMessageBox, QProgressBar, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QCheckBox,
)

from constants import (
    CLASS_PALETTE, EXPECTED_COLUMNS, KNOWN_CLASSES,
    KNOWN_DIRECTIONS, KNOWN_EVENTS, MAX_CSV_BYTES, MAX_TABLE_ROWS,
    safe_float, sanitise_cell,
)
from widgets import (
    MiniBarChart, MiniPieChart, HeatmapWidget, TrajectoryCanvas,
    StatCard, chart_card,
)


class LogAnalysisPanel(QWidget):
    """
    Main panel for analyzing CSV log files.
    
    This widget provides a complete dashboard for analyzing
    detection logs from multiple video sessions.
    """

    def __init__(self, parent=None):
        """
        Initialize the LogAnalysisPanel.
        
        Sets up the filtered rows storage and builds the UI.
        """
        super().__init__(parent)
        self._filtered_rows: list = []  # Store filtered CSV rows
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        """
        Build the complete UI layout for the analysis panel.
        
        Creates:
        - Header with title and description
        - File picker + class filter row
        - Run Analysis button + status label
        - Progress bar
        - 6 stat cards in a row
        - 2 rows of charts (6 total)
        - Data table with export button
        """
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(16)

        # ── Header ───────────────────────────────────────────────────────
        row = QHBoxLayout()
        h = QLabel("Log Analysis")
        h.setStyleSheet("font-size:20px;font-weight:700;color:#111827;")
        s = QLabel("Import CSV logs, filter by class, and explore insights")
        s.setStyleSheet("font-size:13px;color:#6b7280;")
        row.addWidget(h); row.addSpacing(14); row.addWidget(s); row.addStretch()
        root.addLayout(row)

        # Horizontal divider line
        div = QFrame(); div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("color:#e5e7ef;"); root.addWidget(div)

        # ── File picker + class filter ──────────────────────────────────
        top = QHBoxLayout(); top.setSpacing(14)
        top.addWidget(self._build_file_group(), stretch=1)
        top.addWidget(self._build_class_filter())
        root.addLayout(top)

        # ── Run button + status ─────────────────────────────────────────
        ar = QHBoxLayout(); ar.setSpacing(14)
        self.btn_analyse = QPushButton("▶  Run Analysis")
        self.btn_analyse.setObjectName("btn_analyse")
        self.btn_analyse.setFixedHeight(40)
        self.btn_analyse.setFixedWidth(176)
        self.status_lbl = QLabel("Ready — add CSV log files to begin.")
        self.status_lbl.setStyleSheet("color:#6b7280;font-size:12px;")
        ar.addWidget(self.btn_analyse)
        ar.addSpacing(10)
        ar.addWidget(self.status_lbl, stretch=1)
        root.addLayout(ar)

        # ── Progress bar ───────────────────────────────────────────────
        self.progress = QProgressBar()
        self.progress.setFixedHeight(6)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        root.addWidget(self.progress)

        # ── Stat cards (6 cards in a row) ───────────────────────────────
        cr = QHBoxLayout(); cr.setSpacing(10)
        self.c_files   = StatCard("📂", "Files",    "0", "slate")
        self.c_tracks  = StatCard("🔢", "Tracks",   "0", "blue")
        self.c_frames  = StatCard("🎞", "Frames",   "0", "purple")
        self.c_entries = StatCard("⬇", "Entries",  "0", "green")
        self.c_exits   = StatCard("⬆", "Exits",    "0", "red")
        self.c_net     = StatCard("≡", "Net Flow", "—", "amber")
        for c in (self.c_files, self.c_tracks, self.c_frames,
                  self.c_entries, self.c_exits, self.c_net):
            cr.addWidget(c)
        root.addLayout(cr)

        # ── Charts row 1 (3 charts) ────────────────────────────────────
        r1 = QHBoxLayout(); r1.setSpacing(14)
        self.bar_chart = MiniBarChart()
        r1.addWidget(chart_card("Class Distribution", self.bar_chart), stretch=2)
        self.pie_chart = MiniPieChart()
        r1.addWidget(chart_card("Traffic Mix", self.pie_chart), stretch=1)
        self.dir_chart = MiniBarChart()
        r1.addWidget(chart_card("Direction Split (UP / DOWN)", self.dir_chart), stretch=1)
        root.addLayout(r1)

        # ── Charts row 2 (3 charts) ────────────────────────────────────
        r2 = QHBoxLayout(); r2.setSpacing(14)
        self.heatmap = HeatmapWidget()
        r2.addWidget(chart_card("Position Heatmap", self.heatmap), stretch=1)
        self.traj = TrajectoryCanvas()
        r2.addWidget(chart_card("Trajectory Map", self.traj), stretch=1)
        self.conf_chart = MiniBarChart()
        r2.addWidget(chart_card("Avg Confidence % by Class", self.conf_chart), stretch=1)
        root.addLayout(r2)

        # ── Data table ─────────────────────────────────────────────────
        tbl_grp = QGroupBox("Detection Records")
        tl = QVBoxLayout(tbl_grp)
        
        # Export button row
        ex_row = QHBoxLayout(); ex_row.addStretch()
        self.btn_export = QPushButton("⬇  Export Filtered CSV")
        self.btn_export.setObjectName("btn_export")
        self.btn_export.setFixedHeight(30)
        self.btn_export.setEnabled(False)  # Disabled until analysis runs
        ex_row.addWidget(self.btn_export)
        tl.addLayout(ex_row)

        # Table widget
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        
        # Define columns
        cols = ["File", "Frame", "Timestamp (s)", "Scene", "Group", "Track", "Class",
                "Conf", "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2", "cx", "cy",
                "W", "H", "Crossed", "Direction", "Speed (px/s)"]
        self.table.setColumnCount(len(cols))
        self.table.setHorizontalHeaderLabels(cols)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(200)
        tl.addWidget(self.table)
        root.addWidget(tbl_grp)

        # ── Connect signals ─────────────────────────────────────────────
        self.btn_add.clicked.connect(self._add_files)
        self.btn_folder.clicked.connect(self._add_folder)
        self.btn_clear.clicked.connect(self._clear_logs)
        self.btn_analyse.clicked.connect(self._run_analysis)
        self.btn_export.clicked.connect(self._export)

    def _build_file_group(self) -> QGroupBox:
        """
        Build the "Log Files" group box.
        
        Contains:
        - QListWidget showing loaded CSV files
        - Add Files, Add Folder, and Clear buttons
        """
        fg = QGroupBox("Log Files")
        fl = QVBoxLayout(fg); fl.setSpacing(8)

        # File list widget
        self.log_list = QListWidget()
        self.log_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.log_list.setFixedHeight(118)

        # Button row
        br = QHBoxLayout(); br.setSpacing(8)
        self.btn_add    = QPushButton("＋  Add Files")
        self.btn_folder = QPushButton("📁  Folder")
        self.btn_clear  = QPushButton("✕  Clear")
        
        # Style the clear button in red
        self.btn_clear.setStyleSheet(
            "QPushButton{color:#dc2626;border-color:#fecaca;background:#fef2f2;}"
            "QPushButton:hover{background:#fee2e2;}"
        )
        
        for b in (self.btn_add, self.btn_folder, self.btn_clear):
            b.setFixedHeight(30); br.addWidget(b)
        fl.addWidget(self.log_list)
        fl.addLayout(br)
        return fg

    def _build_class_filter(self) -> QGroupBox:
        """
        Build the "Class Filter" group box.
        
        Contains checkboxes for each object class plus "ALL".
        """
        cg = QGroupBox("Class Filter")
        cl = QVBoxLayout(cg); cl.setSpacing(6)
        cg.setFixedWidth(166)
        
        self._checks: dict = {}
        for cls in ["ALL", "car", "bus", "truck", "motorcycle", "bicycle", "person"]:
            cb = QCheckBox(cls.capitalize())
            col = CLASS_PALETTE.get(cls, "#6b7280")
            cb.setStyleSheet(
                f"QCheckBox{{color:{col};font-weight:500;}}"
                f"QCheckBox::indicator:checked{{background:{col};"
                f"border-color:{col};}}"
            )
            cb.setChecked(True)
            self._checks[cls] = cb
            
            # Connect ALL checkbox to toggle all others
            if cls == "ALL":
                cb.stateChanged.connect(self._toggle_all)
            cl.addWidget(cb)
        cl.addStretch()
        return cg

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _toggle_all(self, state):
        """
        Toggle all class checkboxes when ALL is clicked.
        
        Parameters
        ----------
        state : int
            Qt.Checked, Qt.Unchecked, or Qt.PartiallyChecked
        """
        checked = (state == Qt.Checked)
        for name, cb in self._checks.items():
            if name != "ALL":
                cb.blockSignals(True); cb.setChecked(checked); cb.blockSignals(False)

    def _selected_classes(self) -> set:
        """
        Get the set of currently selected class names.
        
        Returns
        -------
        set
            Set of selected class names (excluding "ALL")
        """
        return {n for n, cb in self._checks.items() if n != "ALL" and cb.isChecked()}

    def _exists(self, path: str) -> bool:
        """
        Check if a file path is already in the list.
        
        Parameters
        ----------
        path : str
            File path to check
            
        Returns
        -------
        bool
            True if the path is already in the list
        """
        return any(self.log_list.item(i).text() == path
                   for i in range(self.log_list.count()))

    def _validate_csv_path(self, path: str):
        """
        Validate a CSV file path.
        
        Checks:
        - File exists and is a regular file
        - Has .csv extension
        - Is within size limit
        
        Parameters
        ----------
        path : str
            Path to CSV file
            
        Returns
        -------
        str or None
            Error message if invalid, None if valid
        """
        if not os.path.isfile(path):
            return f"Not a regular file: {os.path.basename(path)}"
        if not path.lower().endswith(".csv"):
            return f"Not a CSV file: {os.path.basename(path)}"
        size = os.path.getsize(path)
        if size > MAX_CSV_BYTES:
            mb = size / (1024 * 1024)
            return (f"{os.path.basename(path)} is {mb:.1f} MB "
                    f"(limit {MAX_CSV_BYTES // (1024 * 1024)} MB)")
        return None

    # ------------------------------------------------------------------
    # File management
    # ------------------------------------------------------------------

    def _add_files(self):
        """
        Open file dialog to add CSV files to the list.
        """
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select Log CSV files", "", "CSV Files (*.csv);;All Files (*)")
        rejected = []
        for f in files:
            err = self._validate_csv_path(f)
            if err:
                rejected.append(err); continue
            if not self._exists(f):
                self.log_list.addItem(f)
        if rejected:
            QMessageBox.warning(self, "Files rejected",
                                "The following files were not added:\n\n"
                                + "\n".join(f"• {e}" for e in rejected))
        self.c_files.set_value(str(self.log_list.count()))

    def _add_folder(self):
        """
        Open folder dialog to add all CSV files from a directory.
        """
        folder = QFileDialog.getExistingDirectory(self, "Select Logs Folder")
        if folder:
            for f in sorted(glob.glob(os.path.join(folder, "*.csv"))):
                if not self._validate_csv_path(f) and not self._exists(f):
                    self.log_list.addItem(f)
        self.c_files.set_value(str(self.log_list.count()))

    def _clear_logs(self):
        """
        Clear all files from the list.
        """
        self.log_list.clear()
        self.c_files.set_value("0")

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def _run_analysis(self):
        """
        Run the analysis on loaded CSV files.
        
        This is the main analysis method that:
        1. Reads all CSV files
        2. Filters by selected classes
        3. Updates the data table
        4. Aggregates statistics
        5. Updates all charts and stat cards
        """
        files = [self.log_list.item(i).text() for i in range(self.log_list.count())]
        if not files:
            self.status_lbl.setText("⚠  No log files loaded."); return
        allowed = self._selected_classes()
        if not allowed:
            self.status_lbl.setText("⚠  No class selected."); return

        self.status_lbl.setText("Processing…")
        self.table.setRowCount(0)
        self.progress.setValue(0)

        all_rows, frames_set, track_meta = self._read_files(files, allowed)
        if all_rows is None:
            return   # error already set in status_lbl

        self._update_table(all_rows)
        agg = self._aggregate(track_meta)
        self._update_cards(agg, len(files), frames_set, all_rows)
        self._update_charts(agg, all_rows)

        self._filtered_rows = all_rows
        self.btn_export.setEnabled(bool(all_rows))

        cap_note = (f"  (table capped at {MAX_TABLE_ROWS:,} rows)"
                    if len(all_rows) > MAX_TABLE_ROWS else "")
        n_tracks = len(track_meta)
        self.status_lbl.setText(
            f"✔  {n_tracks} unique objects · {len(frames_set)} frames "
            f"· {len(all_rows):,} records · {len(files)} file(s){cap_note}"
        )

    def _read_files(self, files, allowed):
        """
        Parse all CSV files and extract detection data.
        
        Parameters
        ----------
        files : list
            List of CSV file paths
        allowed : set
            Set of allowed class names to include
            
        Returns
        -------
        tuple
            (all_rows, frames_set, track_meta) or (None, None, None) on error
        """
        all_rows   = []
        frames_set = set()
        track_meta = {}

        for fi, fpath in enumerate(files):
            err = self._validate_csv_path(fpath)
            if err:
                self.status_lbl.setText(f"⚠  Skipped: {err}"); continue

            try:
                with open(fpath, newline="", encoding="utf-8", errors="replace") as fh:
                    reader = csv.DictReader(fh)
                    if reader.fieldnames is None:
                        self.status_lbl.setText(
                            f"⚠  Empty or invalid CSV: {os.path.basename(fpath)}")
                        return None, None, None
                    missing = EXPECTED_COLUMNS - set(reader.fieldnames)
                    if missing:
                        self.status_lbl.setText(
                            f"⚠  Missing columns in {os.path.basename(fpath)}: "
                            f"{', '.join(sorted(missing))}")
                        return None, None, None

                    for row in reader:
                        cls = row.get("class_name", "").strip()
                        if cls not in KNOWN_CLASSES or cls not in allowed:
                            continue

                        direction = row.get("direction", "").strip().upper()
                        if direction not in KNOWN_DIRECTIONS:
                            direction = "NONE"
                        evt = row.get("crossed_line", "").strip().lower()
                        if evt not in ("true", "false"):
                            evt = "false"

                        cx   = safe_float(row.get("cx",   ""), 0, 640)
                        cy   = safe_float(row.get("cy",   ""), 0, 480)
                        conf = safe_float(row.get("confidence", ""), 0, 1)

                        clean_row = {k: sanitise_cell(v) for k, v in row.items()}
                        clean_row.update(direction=direction, crossed_line=evt, class_name=cls)
                        all_rows.append(clean_row)

                        tid = row.get("track_id", "").strip()
                        key = (fpath, tid)
                        frames_set.add((fpath, row.get("frame", "")))

                        if key not in track_meta:
                            track_meta[key] = {
                                "cls": cls, "confs": [],
                                "dir_votes": Counter(),
                                "points": [], "entries": 0, "exits": 0,
                            }
                        tm = track_meta[key]
                        if conf > 0:
                            tm["confs"].append(conf)
                        if direction and direction != "NONE":
                            tm["dir_votes"][direction] += 1
                        if evt == "true":
                            if direction == "DOWN": tm["entries"] += 1
                            else:                   tm["exits"]   += 1
                        if cx > 0 or cy > 0:
                            tm["points"].append((cx, cy))

            except Exception as exc:
                self.status_lbl.setText(
                    f"⚠  Error: {os.path.basename(fpath)}: {exc}")
                return None, None, None

            self.progress.setValue(int((fi + 1) / len(files) * 100))

        return all_rows, frames_set, track_meta

    def _aggregate(self, track_meta: dict) -> dict:
        """
        Aggregate per-track metadata into summary statistics.
        
        Parameters
        ----------
        track_meta : dict
            Dictionary of track metadata from _read_files
            
        Returns
        -------
        dict
            Aggregated statistics including class counts, directions, etc.
        """
        class_counts = Counter()
        class_conf   = defaultdict(list)
        dir_counts   = Counter()
        entries = exits = 0
        track_data: dict = {}

        for key, tm in track_meta.items():
            cls = tm["cls"]
            class_counts[cls] += 1
            if tm["confs"]:
                class_conf[cls].append(sum(tm["confs"]) / len(tm["confs"]))
            if tm["dir_votes"]:
                dir_counts[tm["dir_votes"].most_common(1)[0][0]] += 1
            if tm["entries"] > 0: entries += 1
            if tm["exits"]   > 0: exits   += 1
            track_data[str(key)] = {"cls": cls, "points": tm["points"]}

        return dict(
            class_counts=class_counts,
            class_conf=class_conf,
            dir_counts=dir_counts,
            entries=entries,
            exits=exits,
            track_data=track_data,
            n_tracks=len(track_meta),
        )

    def _update_table(self, all_rows: list):
        """
        Populate the data table with detection records.
        
        Parameters
        ----------
        all_rows : list
            List of detection row dictionaries
        """
        display_rows = all_rows[:MAX_TABLE_ROWS]
        self.table.setRowCount(len(display_rows))
        col_keys = ["video_name", "frame", "timestamp_sec", "scene_name", "group_id",
                    "track_id", "class_name", "confidence",
                    "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2", "cx", "cy",
                    "frame_width", "frame_height", "crossed_line", "direction", "speed_px_s"]
        for ri, row in enumerate(display_rows):
            for ci, col in enumerate(col_keys):
                val  = row.get(col, "")
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignCenter)
                
                # Color code crossed_line events
                evt = row.get("crossed_line", "").strip().lower()
                if evt == "true":   item.setForeground(QColor("#16a34a"))
                
                # Color code classes (now at index 6)
                if ci == 6:
                    item.setForeground(QColor(CLASS_PALETTE.get(val, "#374151")))
                self.table.setItem(ri, ci, item)

    def _update_cards(self, agg: dict, n_files: int, frames_set: set, all_rows: list):
        """
        Update the stat cards with aggregated data.
        
        Parameters
        ----------
        agg : dict
            Aggregated statistics from _aggregate
        n_files : int
            Number of files analyzed
        frames_set : set
            Set of (file, frame_id) tuples
        all_rows : list
            All detection rows
        """
        self.c_files.set_value(str(n_files))
        self.c_tracks.set_value(str(agg["n_tracks"]))
        self.c_frames.set_value(str(len(frames_set)))
        self.c_entries.set_value(str(agg["entries"]))
        self.c_exits.set_value(str(agg["exits"]))
        net = agg["entries"] - agg["exits"]
        self.c_net.set_value(f"{net:+d}" if all_rows else "—")

    def _update_charts(self, agg: dict, all_rows: list):
        """
        Update all charts with visualization data.
        
        Parameters
        ----------
        agg : dict
            Aggregated statistics
        all_rows : list
            All detection rows
        """
        # Class distribution bar chart
        order  = ["car", "bus", "truck", "motorcycle", "bicycle", "person"]
        labels = [c for c in order if agg["class_counts"].get(c, 0) > 0]
        values = [agg["class_counts"][c] for c in labels]
        colors = [CLASS_PALETTE[c] for c in labels]
        self.bar_chart.set_data(labels, values, colors)
        self.pie_chart.set_data(labels, values, colors)

        # Direction split chart
        dl = [k for k in ["UP", "DOWN"] if agg["dir_counts"].get(k, 0) > 0]
        dv = [agg["dir_counts"][k] for k in dl]
        dc = ["#dc2626" if k == "UP" else "#2563eb" for k in dl]
        self.dir_chart.set_data(dl, dv, dc)

        # Heatmap from center points
        pts = [(safe_float(row.get("cx", ""), 0, 640),
                safe_float(row.get("cy", ""), 0, 480))
               for row in all_rows]
        pts = [(cx, cy) for cx, cy in pts if cx > 0 or cy > 0]
        self.heatmap.set_points(pts)
        self.traj.set_tracks(agg["track_data"])

        # Confidence chart
        cl = [c for c in labels if agg["class_conf"].get(c)]
        cv = [round(sum(agg["class_conf"][c]) / len(agg["class_conf"][c]) * 100)
              for c in cl]
        self.conf_chart.set_data(cl, cv, [CLASS_PALETTE[c] for c in cl])

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _export(self):
        if not self._filtered_rows:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "filtered_log.csv", "CSV Files (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        try:
            with open(path, "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=self._filtered_rows[0].keys(),
                                   extrasaction="ignore")
                w.writeheader()
                w.writerows(self._filtered_rows)
            self.status_lbl.setText(
                f"✔  Exported {len(self._filtered_rows):,} rows → {path}")
        except Exception as exc:
            self.status_lbl.setText(f"⚠  Export error: {exc}")
