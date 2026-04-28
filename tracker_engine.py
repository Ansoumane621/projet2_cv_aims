"""
tracker_engine.py
~~~~~~~~~~~~~~~~~
Encapsulates all per-frame tracking logic:
  - DeepSORT track management
  - Direction inference
  - Counting-line crossing detection
  - Memory / stale-track cleanup
  - OpenCV frame annotation

No PyQt5 dependency — returns annotated NumPy frames.
"""
import time
from typing import Optional

import cv2
import numpy as np
from deep_sort_realtime.deepsort_tracker import DeepSort

from constants import (
    ALLOWED_CLASSES, MAX_ACTIVE_TRACKS,
    COLOR_MAP_CV2,
)
from detector import Detector
from session_manager import SessionManager


class TrackerEngine:
    """
    Wraps DeepSORT + YOLO inference and all crossing / counting logic.

    Typical usage per frame
    -----------------------
    annotated, fps = engine.process_frame(frame, line_y, allowed_classes)
    """

    FRAME_W = 640
    FRAME_H = 480

    def __init__(self) -> None:
        self.detector = Detector()
        self._reset_tracker()

        # ── Skip-frame control ────────────────────────────────────────────
        self.skip_frames     = 2       # run YOLO every N frames
        self.last_detections: list = []
        self.last_fps        = 0.0
        self.frame_id        = 0

        # ── Per-track state ───────────────────────────────────────────────
        self.trajectories:       dict = {}   # track_id -> [(cx,cy), ...]
        self.track_classes:      dict = {}   # track_id -> class name
        self.track_confidences:  dict = {}   # track_id -> float
        self.track_directions:   dict = {}   # track_id -> "UP"|"DOWN"|"NONE"
        self.track_counted:      dict = {}   # track_id -> "UP"|"DOWN"
        self.pending_events:     dict = {}   # track_id -> [event, ...]
        self.prev_cy_map:        dict = {}   # track_id -> cy (previous frame)
        self.prev_bottom_map:    dict = {}   # track_id -> b  (previous frame)

        # ── Counters ──────────────────────────────────────────────────────
        self.enter_count = 0
        self.exit_count  = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Full state reset — call at the start of each new session."""
        self._reset_tracker()
        self.last_detections = []
        self.last_fps        = 0.0
        self.frame_id        = 0
        self.trajectories.clear()
        self.track_classes.clear()
        self.track_confidences.clear()
        self.track_directions.clear()
        self.track_counted.clear()
        self.pending_events.clear()
        self.prev_cy_map.clear()
        self.prev_bottom_map.clear()
        self.enter_count = 0
        self.exit_count  = 0

    def process_frame(
        self,
        frame: np.ndarray,
        line_y: int,
        allowed_live: list,
        session: Optional[SessionManager] = None,
    ) -> tuple[np.ndarray, float, int]:
        """
        Run detection + tracking on one frame.

        Returns
        -------
        annotated : BGR frame with bounding boxes, trajectories, overlay
        fps_val   : current FPS (float)
        total     : number of confirmed tracks drawn this frame
        """
        self.frame_id += 1
        frame     = cv2.resize(frame, (self.FRAME_W, self.FRAME_H))
        annotated = frame.copy()
        timestamp = round(time.time(), 4)

        # ── YOLO detection (every skip_frames) ───────────────────────────
        if self.frame_id % self.skip_frames == 0:
            detections, fps_val = self._run_yolo(frame, allowed_live)
            self.last_detections = detections
            self.last_fps        = fps_val
            if session:
                session.periodic_flush(self.frame_id, self.skip_frames)
        else:
            detections = self.last_detections
            fps_val    = self.last_fps

        # ── DeepSORT tracking ─────────────────────────────────────────────
        tracks = self.tracker.update_tracks(detections, frame=frame)

        # ── Stale-track cleanup ───────────────────────────────────────────
        active_ids = {t.track_id for t in tracks if t.is_confirmed()}
        self._cleanup_stale_tracks(active_ids)

        # ── Counting line ─────────────────────────────────────────────────
        cv2.line(annotated, (0, line_y), (self.FRAME_W, line_y), (0, 255, 255), 2)
        cv2.putText(annotated, f"COUNT LINE  y={line_y}",
                    (5, line_y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

        total = 0
        for t in tracks:
            if not t.is_confirmed():
                continue
            total += self._process_track(
                t, line_y, timestamp, annotated, session
            )

        # ── Stats overlay ─────────────────────────────────────────────────
        self._draw_stats_overlay(annotated, total)

        return annotated, fps_val, total

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _reset_tracker(self) -> None:
        """(Re-)create a fresh DeepSORT instance."""
        self.tracker = DeepSort(max_age=20, n_init=1, nn_budget=100)

    def _run_yolo(self, frame: np.ndarray, allowed_live: list) -> tuple[list, float]:
        """Run YOLO on *frame* and return (detections, fps)."""
        results, fps_val = self.detector.detect(frame)
        detections = []
        for box in results[0].boxes:
            cls_id = int(box.cls[0])
            conf   = float(box.conf[0])
            name   = self.detector.model.names[cls_id]
            if name not in ALLOWED_CLASSES:
                continue
            if conf < 0.4:
                continue
            if name not in allowed_live:
                continue
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            detections.append(([x1, y1, x2 - x1, y2 - y1], conf, name))
        return detections, fps_val

    def _process_track(
        self,
        t,
        line_y: int,
        timestamp: float,
        annotated: np.ndarray,
        session: Optional[SessionManager],
    ) -> int:
        """Process a single confirmed track. Returns 1 if drawn, 0 if skipped."""
        track_id     = t.track_id
        l, top, r, b = map(int, t.to_ltrb())
        l, r   = max(0, l),   min(self.FRAME_W - 1, r)
        top, b = max(0, top), min(self.FRAME_H - 1, b)
        cx    = (l + r)   // 2
        cy    = (top + b) // 2
        w_box = r - l
        h_box = b - top

        # ── Persist class / confidence ────────────────────────────────────
        if t.det_class is not None:
            self.track_classes[track_id] = t.det_class
        if t.det_conf is not None:
            self.track_confidences[track_id] = round(float(t.det_conf), 3)

        class_name = self.track_classes.get(track_id, "object")
        confidence = self.track_confidences.get(track_id, 0.0)

        if class_name == "object":
            return 0

        # ── Trajectory (display only) ─────────────────────────────────────
        if track_id not in self.trajectories:
            self.trajectories[track_id] = []
        if self.frame_id % self.skip_frames == 0:
            self.trajectories[track_id].append((cx, cy))
            if len(self.trajectories[track_id]) > 20:
                self.trajectories[track_id].pop(0)

        # ── Direction ─────────────────────────────────────────────────────
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

        self.prev_cy_map[track_id]     = cy
        self.prev_bottom_map[track_id] = b

        # ── Crossing detection ────────────────────────────────────────────
        event = self._check_crossing(
            track_id, direction, cy, b, prev_cy, prev_bottom, line_y, class_name
        )

        # ── Log row ───────────────────────────────────────────────────────
        if (session and self.frame_id % self.skip_frames == 0):
            pending = self.pending_events.pop(track_id, [])
            if event != "none":
                pending = [e for e in pending if e != event]

            session.write_row(
                self.frame_id, timestamp, track_id, class_name,
                (l, top, r, b), (w_box, h_box), (cx, cy),
                confidence, direction, event,
            )
            for extra_event in pending:
                session.write_row(
                    self.frame_id, timestamp, track_id, class_name,
                    (l, top, r, b), (w_box, h_box), (cx, cy),
                    confidence, direction, extra_event,
                )

        # ── Annotation ───────────────────────────────────────────────────
        self._draw_track(annotated, track_id, class_name, confidence,
                         l, top, r, b)
        return 1

    def _check_crossing(
        self, track_id, direction, cy, b, prev_cy, prev_bottom,
        line_y, class_name
    ) -> str:
        """Detect line crossings and update counters. Returns event string."""
        event = "none"

        centre_down = direction == "DOWN" and prev_cy     < line_y and cy >= line_y
        bottom_down = direction == "DOWN" and prev_bottom < line_y and b  >= line_y
        centre_up   = direction == "UP"   and prev_cy     > line_y and cy <= line_y
        bottom_up   = direction == "UP"   and prev_bottom > line_y and b  <= line_y

        if centre_down or bottom_down:
            if self.track_counted.get(track_id) != "DOWN":
                self.enter_count += 1
                self.track_counted[track_id] = "DOWN"
                event = "entry"
                self.pending_events.setdefault(track_id, []).append("entry")
                print(f"[COUNT] ENTRY track={track_id} class={class_name} "
                      f"cy={cy} total_in={self.enter_count}")

        elif centre_up or bottom_up:
            if self.track_counted.get(track_id) != "UP":
                self.exit_count += 1
                self.track_counted[track_id] = "UP"
                event = "exit"
                self.pending_events.setdefault(track_id, []).append("exit")
                print(f"[COUNT] EXIT  track={track_id} class={class_name} "
                      f"cy={cy} total_out={self.exit_count}")

        return event

    def _draw_track(
        self, annotated, track_id, class_name, confidence,
        l, top, r, b
    ) -> None:
        """Draw bounding box, label, and trajectory tail."""
        color = COLOR_MAP_CV2.get(class_name, (200, 200, 200))
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

    def _draw_stats_overlay(self, annotated, total: int) -> None:
        """Draw IN / OUT / NET overlay on the top-left corner."""
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

    def _cleanup_stale_tracks(self, active_ids: set) -> None:
        """Remove per-track state for tracks no longer reported by DeepSORT."""
        purgeable = [
            self.trajectories, self.track_classes, self.track_confidences,
            self.track_directions, self.prev_cy_map, self.prev_bottom_map,
        ]
        stale = set()
        for d in purgeable:
            stale.update(k for k in d if k not in active_ids)
        for d in purgeable:
            for k in stale:
                d.pop(k, None)
        for k in stale:
            self.pending_events.pop(k, None)

        # Hard cap on track_counted to prevent OOM
        if len(self.track_counted) > MAX_ACTIVE_TRACKS:
            overflow = len(self.track_counted) - MAX_ACTIVE_TRACKS
            oldest   = list(self.track_counted.keys())[:overflow]
            for k in oldest:
                del self.track_counted[k]
            print(f"[SECURITY] track_counted pruned {overflow} oldest entries")
