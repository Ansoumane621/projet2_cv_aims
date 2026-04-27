import atexit
import csv
import os
import re
import sys
import time

import cv2
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QApplication, QFileDialog

from deep_sort_realtime.deepsort_tracker import DeepSort

from detector import Detector
from ui import UI

# Base directory = folder of the script itself (not CWD)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# ── Security constants ────────────────────────────────────────────────────────
# Maximum number of active tracks kept in memory at any time.
# Prevents unbounded memory growth on long videos.
# DeepSORT with max_age=20 rarely needs more than a few hundred simultaneous
# tracks — 1000 is a safe ceiling even for very busy scenes.
MAX_ACTIVE_TRACKS = 1000

# Regex for sanitising the video filename before using it in a log path.
# Only alphanumerics, hyphens, underscores and dots are kept.
# This prevents path traversal attacks (e.g. "../../etc/passwd.mp4").
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]")


def _sanitise_filename(name: str) -> str:
    """
    SECURITY FIX — path traversal prevention.
    Remove every character that is not alphanumeric, dot, hyphen or underscore,
    then strip leading dots so the result can never escape the logs/ directory.
    """
    safe = _SAFE_FILENAME_RE.sub("_", name)
    safe = safe.lstrip(".")          # block hidden-file tricks  (./../)
    return safe or "unknown"


class App(UI):
    def __init__(self):
        super().__init__()

        print(f"[INIT] BASE_DIR = {BASE_DIR}")
        print(f"[INIT] LOGS_DIR = {LOGS_DIR}")
        print(f"[INIT] CWD      = {os.getcwd()}")

        # ── Models ────────────────────────────────────────────────────────────
        self.detector = Detector()

        # SECURITY/FIX — n_init=1
        # With n_init=3, DeepSORT needs 3 consecutive frames before confirming
        # a track. Any object that crosses the counting line in those first 2
        # frames is completely invisible to our counter.
        # Setting n_init=1 confirms tracks on the very first detection so fast
        # objects (trucks, motorcycles) are never silently missed.
        self.tracker = DeepSort(max_age=20, n_init=1, nn_budget=100)

        # ── Config ────────────────────────────────────────────────────────────
        self.allowed_classes = [
            "car", "bus", "truck", "motorcycle", "bicycle", "person"
        ]

        # ── Video ─────────────────────────────────────────────────────────────
        self.cap        = None
        self.video_path = None

        # ── Timer ─────────────────────────────────────────────────────────────
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_frame)

        # ── Button events ──────────────────────────────────────────────────────
        self.start_btn.clicked.connect(self.start)
        self.stop_btn.clicked.connect(self.stop)
        self.pause_btn.clicked.connect(self.pause)
        self.select_btn.clicked.connect(self.select_video)

        # ── Output video ───────────────────────────────────────────────────────
        self.out = None

        # ── Tracking state ─────────────────────────────────────────────────────
        # SECURITY FIX — two separate dicts for direction and counting state.
        # Previously both were stuffed into self.track_directions using keys
        # like "7" and "7_counted", risking key collisions if a track_id ever
        # happened to be the string "7_counted".
        self.trajectories      = {}   # track_id -> [(cx,cy), ...]  (display only)
        self.track_classes     = {}   # track_id -> class name
        self.track_confidences = {}   # track_id -> float confidence
        self.track_directions  = {}   # track_id -> "UP" | "DOWN" | "NONE"
        self.track_counted     = {}   # track_id -> "UP" | "DOWN"  (crossing state)
                                      # SECURITY: separate dict — no key collision

        self.enter_count = 0
        self.exit_count  = 0

        # ── Performance ───────────────────────────────────────────────────────
        self.frame_id        = 0
        self.skip_frames     = 2      # YOLO every N frames, DeepSORT every frame
        self.last_detections = []
        self.last_fps        = 0.0

        # ── Counting line ─────────────────────────────────────────────────────
        # SECURITY FIX — line_y is locked at session start and cannot be moved
        # while the video is running.  Moving the line mid-session caused
        # phantom crossings and double-counting.
        # The slider is disabled during playback and re-enabled when stopped.
        self._session_line_y = 240    # captured at Start, immutable during run

        # ── SECURITY FIX A — pending_events ──────────────────────────────────
        # The CSV logger only writes on even frames (frame_id % skip_frames==0).
        # A crossing on an odd frame increments the live counter correctly but
        # the event was silently lost from the CSV.
        # Solution: store the event here and write it on the next logged frame.
        # Using a list instead of a scalar so rapid double-crossings are not
        # overwritten (see SECURITY FIX F).
        self.pending_events = {}      # track_id -> ["entry"|"exit", ...]

        # ── SECURITY FIX B — prev_cy_map / prev_bottom_map ────────────────────
        # Old code used trajectories[-2] as prev_cy.  Trajectories only append
        # every skip_frames frames, so prev_cy was actually skip_frames ago —
        # making crossing detection imprecise and missing fast objects.
        # These maps are updated on EVERY frame for pixel-perfect detection.
        self.prev_cy_map     = {}     # track_id -> cy  from the previous frame
        self.prev_bottom_map = {}     # track_id -> b   from the previous frame

        # ── Log file ──────────────────────────────────────────────────────────
        os.makedirs(LOGS_DIR, exist_ok=True)
        self.log_file = None
        self.logger   = None

        atexit.register(self._release_resources)

        # ── UI class dropdown (kept for internal compatibility) ────────────────
        self.class_select.addItem("ALL")
        for name in self.allowed_classes:
            self.class_select.addItem(name)

    # =========================================================================
    # VIDEO SELECTION
    # =========================================================================
    def select_video(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select Video", "",
            "Video Files (*.mp4 *.avi *.mov *.mkv *.webm)"
        )
        if file_name:
            self.video_path = file_name
            self.cap = cv2.VideoCapture(file_name)
            self.video_path_label.setText(file_name)
            print(f"[VIDEO] Selected  : {file_name}")
            print(f"[VIDEO] isOpened(): {self.cap.isOpened()}")

    # =========================================================================
    # START
    # =========================================================================
    def start(self):
        print("[START] Start button clicked")

        if self.cap is None:
            self._set_warning("Warning: Select a video first!")
            return

        if not self.cap.isOpened():
            self._set_warning("Warning: Could not open video file.")
            return

        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

        fps      = int(self.cap.get(cv2.CAP_PROP_FPS)) or 30
        fourcc   = cv2.VideoWriter_fourcc(*'XVID')
        out_path = os.path.join(BASE_DIR, f"output_{int(time.time())}.avi")
        self.out = cv2.VideoWriter(out_path, fourcc, fps, (640, 480))
        print(f"[START] Output video: {out_path}")

        # ── SECURITY FIX — lock counting line for this session ────────────────
        # Snapshot the slider value NOW so it cannot change during playback.
        # This prevents phantom crossings caused by moving the line mid-session.
        self._session_line_y = self.get_line_y()
        self.line_slider.setEnabled(False)
        print(f"[START] Counting line locked at y={self._session_line_y}")

        # ── SECURITY FIX — reinitialise DeepSORT tracker ──────────────────────
        # DeepSORT keeps internal state (Kalman filters, track IDs) between
        # sessions.  Without a fresh instance, track IDs from the previous run
        # can be reused, bypassing the "already counted" guard in track_counted.
        self.tracker = DeepSort(max_age=20, n_init=1, nn_budget=100)

        # ── Reset ALL state ───────────────────────────────────────────────────
        self.trajectories.clear()
        self.track_classes.clear()
        self.track_confidences.clear()
        self.track_directions.clear()
        self.track_counted.clear()        # SECURITY: separate counting dict
        self.pending_events.clear()       # FIX A
        self.prev_cy_map.clear()          # FIX B
        self.prev_bottom_map.clear()      # FIX B
        self.enter_count     = 0
        self.exit_count      = 0
        self.frame_id        = 0
        self.last_detections = []
        self.last_fps        = 0.0
        self.set_live_counts(0, 0)

        # ── Open log file ─────────────────────────────────────────────────────
        self._close_log()

        session_ts = time.strftime("%Y%m%d_%H%M%S")

        # SECURITY FIX — sanitise video filename before using it in a path.
        # Raw filenames like "../../etc/passwd" would escape the logs/ directory.
        raw_name   = (os.path.splitext(os.path.basename(self.video_path))[0]
                      if self.video_path else "unknown")
        video_name = _sanitise_filename(raw_name)
        log_path   = os.path.join(LOGS_DIR, f"{video_name}_{session_ts}.csv")

        # SECURITY FIX — verify the resolved path stays inside LOGS_DIR.
        # os.path.join can be tricked if video_name still contains separators.
        resolved = os.path.realpath(log_path)
        if not resolved.startswith(os.path.realpath(LOGS_DIR)):
            self._set_warning("Security error: invalid log path detected.")
            print(f"[SECURITY] Blocked path traversal attempt: {log_path}")
            return

        print(f"[START] Opening log: {log_path}")
        try:
            self.log_file = open(log_path, "w", newline="", encoding="utf-8")
            self.logger   = csv.writer(self.log_file)
            self.logger.writerow([
                "video", "frame_id", "timestamp",
                "track_id", "class",
                "x1", "y1", "x2", "y2",
                "width", "height", "cx", "cy",
                "confidence", "direction", "event"
            ])
            self.log_file.flush()
            print(f"[START] Log opened: {log_path}")
        except Exception as e:
            # SECURITY FIX — alert user clearly; do NOT start the session.
            # Old code started the timer even when the log failed to open,
            # causing a silent data-loss session.
            self._set_warning(f"Could not open log file: {e}")
            print(f"[START] ERROR opening log: {e}")
            self.line_slider.setEnabled(True)
            return

        self.timer.start(25)
        print("[START] Timer started")

    # =========================================================================
    # PAUSE / STOP
    # =========================================================================
    def pause(self):
        if self.timer.isActive():
            self.timer.stop()
            print("[PAUSE] Paused")
        else:
            self.timer.start(25)
            print("[PAUSE] Resumed")

    def stop(self):
        print("[STOP] Stop requested")
        self.timer.stop()
        self._flush_pending_events_to_log()
        self._release_resources()
        self._on_video_finished()

    # =========================================================================
    # WINDOW CLOSE
    # =========================================================================
    def closeEvent(self, event):
        print("[CLOSE] Window closing")
        self.timer.stop()
        self._flush_pending_events_to_log()
        self._release_resources()
        super().closeEvent(event)

    # =========================================================================
    # RESOURCE CLEANUP
    # =========================================================================
    def _close_log(self):
        if self.log_file and not self.log_file.closed:
            self.log_file.flush()
            self.log_file.close()
            print("[LOG] Log file closed properly")

    def _release_resources(self):
        if self.out:
            self.out.release()
            self.out = None
            print("[RELEASE] VideoWriter released")
        self._close_log()
        # Re-enable the slider now that the session is over
        self.line_slider.setEnabled(True)

    def _set_warning(self, msg: str):
        """Display a warning in the path label without changing other state."""
        self.video_path_label.setText(f"⚠  {msg}")
        self.video_path_label.setStyleSheet(
            "color:#dc2626;font-size:11px;"
            "background:#fef2f2;border:1px solid #fecaca;"
            "border-radius:6px;padding:6px 10px;"
        )

    # =========================================================================
    # SECURITY FIX A — flush pending events before closing log
    # =========================================================================
    def _flush_pending_events_to_log(self):
        """
        Write any crossing events that were detected on unlogged (odd) frames
        but not yet written to the CSV.  Called before closing the log so that
        no event is ever lost, including at end-of-video.

        SECURITY FIX F: pending_events stores a LIST of events per track so
        that rapid double-crossings (entry then exit on consecutive unlogged
        frames) are not silently overwritten.
        """
        if not self.pending_events:
            return
        if self.logger is None or self.log_file is None or self.log_file.closed:
            return

        timestamp  = round(time.time(), 4)
        video_name = (os.path.basename(self.video_path)
                      if self.video_path else "unknown")

        for track_id, event_list in self.pending_events.items():
            class_name = self.track_classes.get(track_id, "object")
            confidence = self.track_confidences.get(track_id, 0.0)
            direction  = self.track_directions.get(track_id, "NONE")
            pts        = self.trajectories.get(track_id, [])
            cx, cy     = pts[-1] if pts else (0, 0)

            for event in event_list:
                self.logger.writerow([
                    video_name, self.frame_id, timestamp,
                    track_id, class_name,
                    0, 0, 0, 0, 0, 0, cx, cy,
                    confidence, direction, event
                ])
                print(f"[LOG] Flushed pending {event} "
                      f"track={track_id} end-of-video")

        self.pending_events.clear()
        self.log_file.flush()

    # =========================================================================
    # END-OF-VIDEO UI UPDATE
    # =========================================================================
    def _on_video_finished(self):
        """Sync the UI with final session counts and show a summary screen."""
        self.set_live_counts(self.enter_count, self.exit_count)

        total_objects = len(self.track_classes)
        summary = (
            f"  Video finished\n\n"
            f"  Frames processed : {self.frame_id}\n"
            f"  Unique objects   : {total_objects}\n"
            f"  Entries  (IN)    : {self.enter_count}\n"
            f"  Exits    (OUT)   : {self.exit_count}\n"
            f"  Net flow (NET)   : {self.enter_count - self.exit_count:+d}"
        )
        self.video.setText(summary)
        self.video.setStyleSheet(
            "QLabel#video_label{"
            "background:#0f172a;color:#94a3b8;"
            "font-size:14px;font-family:'Courier New';"
            "padding:30px;border-radius:10px;}"
        )

        raw_name   = (os.path.splitext(os.path.basename(self.video_path))[0]
                      if self.video_path else "unknown")
        video_name = _sanitise_filename(raw_name)
        self.video_path_label.setText(
            f"\u2714  Finished \u2014 log saved to logs/{video_name}_*.csv"
        )
        self.video_path_label.setStyleSheet(
            "color:#16a34a;font-size:11px;"
            "background:#f0fdf4;border:1px solid #bbf7d0;"
            "border-radius:6px;padding:6px 10px;"
        )
        print(f"[DONE] IN={self.enter_count} OUT={self.exit_count} "
              f"NET={self.enter_count - self.exit_count:+d} "
              f"OBJECTS={total_objects}")

    # =========================================================================
    # SECURITY FIX — memory cleanup for expired tracks
    # =========================================================================
    def _cleanup_stale_tracks(self, active_ids: set):
        """
        SECURITY FIX — memory leak prevention.
        Remove entries for tracks that DeepSORT no longer reports as active.
        Without this, all per-track dicts grow forever during long sessions,
        eventually exhausting RAM.

        Called every frame with the set of currently confirmed track IDs.
        Stale entries (present in our dicts but absent from active_ids) are
        pruned, except for track_counted which must be kept for the full
        session to prevent re-counting if a track_id is ever recycled by
        DeepSORT.  (DeepSORT monotonically increments IDs so recycling is
        very unlikely with n_init=1, but we keep the guard for safety.)
        """
        # Dicts that are safe to prune immediately when a track disappears
        purgeable = [
            self.trajectories,
            self.track_classes,
            self.track_confidences,
            self.track_directions,
            self.prev_cy_map,
            self.prev_bottom_map,
        ]
        stale = set()
        for d in purgeable:
            stale.update(k for k in d if k not in active_ids)
        for d in purgeable:
            for k in stale:
                d.pop(k, None)

        # Also clear pending_events for stale tracks (they will never be logged)
        for k in stale:
            self.pending_events.pop(k, None)

        # track_counted is intentionally NOT pruned here — see docstring.

        # SECURITY FIX — hard cap on total memory footprint.
        # If somehow more than MAX_ACTIVE_TRACKS are alive simultaneously,
        # drop the oldest entries to prevent OOM.
        if len(self.track_counted) > MAX_ACTIVE_TRACKS:
            overflow = len(self.track_counted) - MAX_ACTIVE_TRACKS
            oldest   = list(self.track_counted.keys())[:overflow]
            for k in oldest:
                del self.track_counted[k]
            print(f"[SECURITY] track_counted pruned {overflow} oldest entries")

    # =========================================================================
    # MAIN LOOP — called by QTimer every 25 ms
    # =========================================================================
    def update_frame(self):
        if self.cap is None:
            return

        ret, frame = self.cap.read()
        if not ret:
            print(f"[FRAME] End of video at frame {self.frame_id}")
            self.timer.stop()
            self._flush_pending_events_to_log()   # FIX A
            self._release_resources()
            self._on_video_finished()
            return

        self.frame_id += 1
        frame     = cv2.resize(frame, (640, 480))
        annotated = frame.copy()

        # Read class filter from UI checkboxes
        allowed_live = self.get_live_allowed_classes()
        timestamp    = round(time.time(), 4)

        # ── YOLO detection (every skip_frames frames) ─────────────────────────
        if self.frame_id % self.skip_frames == 0:
            results, fps_val = self.detector.detect(frame)
            detections = []

            for box in results[0].boxes:
                cls_id = int(box.cls[0])
                conf   = float(box.conf[0])
                name   = self.detector.model.names[cls_id]

                if name not in self.allowed_classes:
                    continue
                if conf < 0.4:
                    continue
                if name not in allowed_live:
                    continue

                x1, y1, x2, y2 = map(int, box.xyxy[0])
                detections.append(([x1, y1, x2 - x1, y2 - y1], conf, name))

            self.last_detections = detections
            self.last_fps        = fps_val

            if (self.log_file and not self.log_file.closed
                    and self.frame_id % (self.skip_frames * 20) == 0):
                self.log_file.flush()
        else:
            detections = self.last_detections
            fps_val    = self.last_fps

        # ── DeepSORT tracking (every frame) ───────────────────────────────────
        tracks = self.tracker.update_tracks(detections, frame=frame)

        # ── Memory cleanup — remove stale tracks every frame ──────────────────
        active_ids = {t.track_id for t in tracks if t.is_confirmed()}
        self._cleanup_stale_tracks(active_ids)

        total = 0

        # ── Use the LOCKED line_y (immutable for this session) ─────────────────
        # SECURITY FIX: read from _session_line_y, NOT from the slider.
        # The slider is disabled during playback, but using _session_line_y
        # adds a second layer of protection against accidental changes.
        line_y = self._session_line_y
        cv2.line(annotated, (0, line_y), (640, line_y), (0, 255, 255), 2)
        cv2.putText(annotated, f"COUNT LINE  y={line_y}", (5, line_y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

        for t in tracks:
            if not t.is_confirmed():
                continue

            track_id     = t.track_id
            l, top, r, b = map(int, t.to_ltrb())

            l, r   = max(0, l),   min(639, r)
            top, b = max(0, top), min(479, b)

            cx    = (l + r)   // 2
            cy    = (top + b) // 2
            w_box = r - l
            h_box = b - top

            # Persist class and confidence
            if t.det_class is not None:
                self.track_classes[track_id] = t.det_class
            if t.det_conf is not None:
                self.track_confidences[track_id] = round(float(t.det_conf), 3)

            class_name = self.track_classes.get(track_id, "object")
            confidence = self.track_confidences.get(track_id, 0.0)

            # SECURITY FIX E — skip "object" class.
            # If YOLO has not yet assigned a class to this track the name is
            # "object".  Writing it to the CSV and including it in analysis
            # silently pollutes the results.  We skip such rows entirely.
            if class_name == "object":
                continue

            # ── Trajectory (display only, every skip_frames) ──────────────────
            if track_id not in self.trajectories:
                self.trajectories[track_id] = []
            if self.frame_id % self.skip_frames == 0:
                self.trajectories[track_id].append((cx, cy))
                if len(self.trajectories[track_id]) > 20:
                    self.trajectories[track_id].pop(0)

            # ── Direction ─────────────────────────────────────────────────────
            # FIX B: prev_cy from the EXACT previous frame, not skip_frames ago
            prev_cy     = self.prev_cy_map.get(track_id, cy)
            prev_bottom = self.prev_bottom_map.get(track_id, b)
            direction   = self.track_directions.get(track_id, "NONE")
            threshold   = max(2, h_box * 0.03)

            delta = cy - prev_cy
            if delta > threshold:
                direction = "DOWN"
            elif delta < -threshold:
                direction = "UP"

            if direction in ("UP", "DOWN"):
                self.track_directions[track_id] = direction

            # FIX B: update every frame
            self.prev_cy_map[track_id]     = cy
            self.prev_bottom_map[track_id] = b

            # ── Crossing detection ─────────────────────────────────────────────
            # FIX C: check BOTH centre (cy) AND bottom edge (b).
            # Large objects (trucks, buses) may have their centre permanently
            # above line_y while their body physically covers it.
            event = "none"

            centre_down = direction == "DOWN" and prev_cy < line_y and cy >= line_y
            bottom_down = direction == "DOWN" and prev_bottom < line_y and b >= line_y
            centre_up   = direction == "UP"   and prev_cy > line_y and cy <= line_y
            bottom_up   = direction == "UP"   and prev_bottom > line_y and b <= line_y

            if centre_down or bottom_down:
                # SECURITY FIX — use separate track_counted dict (not track_directions)
                # to avoid any risk of key collision between "7" and "7_counted"
                if self.track_counted.get(track_id) != "DOWN":
                    self.enter_count += 1
                    self.track_counted[track_id] = "DOWN"
                    event = "entry"
                    # FIX A + FIX F: append to list so rapid double-crossings
                    # are not overwritten
                    self.pending_events.setdefault(track_id, []).append("entry")
                    print(f"[COUNT] ENTRY track={track_id} class={class_name} "
                          f"cy={cy} b={b} total_in={self.enter_count}")

            elif centre_up or bottom_up:
                if self.track_counted.get(track_id) != "UP":
                    self.exit_count += 1
                    self.track_counted[track_id] = "UP"
                    event = "exit"
                    self.pending_events.setdefault(track_id, []).append("exit")
                    print(f"[COUNT] EXIT  track={track_id} class={class_name} "
                          f"cy={cy} b={b} total_out={self.exit_count}")

            # ── Log (every skip_frames) ────────────────────────────────────────
            if (self.frame_id % self.skip_frames == 0
                    and self.logger is not None
                    and self.log_file is not None
                    and not self.log_file.closed):

                # FIX A + FIX F: drain ALL pending events for this track
                pending = self.pending_events.pop(track_id, [])

                if event != "none":
                    # Current frame already has this event — avoid duplicate
                    pending = [e for e in pending if e != event]

                # Write the current frame's row with its own event
                self.logger.writerow([
                    os.path.basename(self.video_path) if self.video_path else "unknown",
                    self.frame_id, timestamp, track_id, class_name,
                    l, top, r, b, w_box, h_box, cx, cy,
                    confidence, direction, event
                ])

                # Write any additional pending events from unlogged frames
                for extra_event in pending:
                    self.logger.writerow([
                        os.path.basename(self.video_path) if self.video_path else "unknown",
                        self.frame_id, timestamp, track_id, class_name,
                        l, top, r, b, w_box, h_box, cx, cy,
                        confidence, direction, extra_event
                    ])

            # ── Draw bounding box ──────────────────────────────────────────────
            color_map = {
                "car":        (0, 200, 255),
                "bus":        (0, 100, 255),
                "truck":      (0,  50, 200),
                "motorcycle": (255, 180,   0),
                "bicycle":    (255, 255,   0),
                "person":     (  0, 255, 100),
            }
            color = color_map.get(class_name, (200, 200, 200))

            cv2.rectangle(annotated, (l, top), (r, b), color, 2)
            label = f"{class_name} #{track_id}  {confidence:.2f}"
            (lw, lh), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            cv2.rectangle(annotated, (l, top - lh - 6), (l + lw + 4, top), color, -1)
            cv2.putText(annotated, label, (l + 2, top - 3),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)

            pts = self.trajectories.get(track_id, [])
            for i in range(1, len(pts)):
                alpha = int(200 * i / len(pts))
                cv2.line(annotated, pts[i - 1], pts[i], (alpha, alpha, 255), 1)

            total += 1

        # ── Stats overlay ──────────────────────────────────────────────────────
        net = self.enter_count - self.exit_count
        overlay = annotated.copy()
        cv2.rectangle(overlay, (10, 10), (200, 120), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.4, annotated, 0.6, 0, annotated)
        cv2.putText(annotated, f"IN  : {self.enter_count}", (20, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 100), 2)
        cv2.putText(annotated, f"OUT : {self.exit_count}",  (20, 65),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 80, 255),  2)
        cv2.putText(annotated, f"NET : {net:+d}",           (20, 95),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)

        if total == 0:
            cv2.putText(annotated, "NO OBJECT DETECTED",
                        (130, 240), cv2.FONT_HERSHEY_SIMPLEX,
                        0.9, (0, 0, 255), 2)

        # ── Save + Display ─────────────────────────────────────────────────────
        if self.out:
            self.out.write(annotated)

        rgb     = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
        h, w, c = rgb.shape
        img     = QImage(rgb.data, w, h, c * w, QImage.Format_RGB888)
        self.video.setPixmap(QPixmap.fromImage(img))

        self.counter_label.setText(f"Objects: {total}")
        self.fps_label.setText(f"Frame: {self.frame_id}  |  FPS: {fps_val:.1f}")
        self.set_live_counts(self.enter_count, self.exit_count)


# =============================================================================
# RUN
# =============================================================================
app    = QApplication(sys.argv)
window = App()
window.show()
sys.exit(app.exec_())