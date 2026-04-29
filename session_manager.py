"""
session_manager.py
~~~~~~~~~~~~~~~~~~
Manages a single detection session:
  - opens / closes the CSV log file
  - writes rows (including pending events from unlogged frames)
  - flushes on stop / end-of-video

This module has NO PyQt5 dependency — it is pure Python I/O logic.

CSV schema follows the professor's required format:
    frame, timestamp_sec, scene_name, group_id, video_name,
    track_id, class_name, confidence,
    bbox_x1, bbox_y1, bbox_x2, bbox_y2, cx, cy,
    frame_width, frame_height,
    crossed_line, direction, speed_px_s
"""
import csv
import os
import time
from typing import Optional

from constants import LOGS_DIR, sanitise_filename

# CSV column order — matches the professor's required schema exactly
CSV_COLUMNS = [
    "frame", "timestamp_sec", "scene_name", "group_id", "video_name",
    "track_id", "class_name", "confidence",
    "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2", "cx", "cy",
    "frame_width", "frame_height",
    "crossed_line", "direction", "speed_px_s",
]


class SessionManager:
    """Opens, writes to, and closes the CSV log for one detection session."""

    def __init__(self) -> None:
        os.makedirs(LOGS_DIR, exist_ok=True)
        self._log_file: Optional[object] = None
        self._writer:   Optional[csv.writer] = None
        self.video_basename: str = "unknown"

        # Session-level metadata (set via open())
        self.scene_name:  str = "unknown"
        self.group_id:    str = "group_01"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self, video_path: Optional[str],
             scene_name: str = "unknown",
             group_id: str = "group_01") -> Optional[str]:
        """
        Create a new session log file.

        Parameters
        ----------
        video_path : str or None
            Path to the source video file
        scene_name : str
            Name of the scene/location (e.g. "intersection_A")
        group_id : str
            Group identifier (e.g. "group_01")

        Returns None on success, or an error message string on failure.
        """
        self.close()  # always close any existing log first

        raw_name = (
            os.path.splitext(os.path.basename(video_path))[0]
            if video_path else "unknown"
        )
        self.video_basename = os.path.basename(video_path) if video_path else "unknown"
        self.scene_name     = scene_name
        self.group_id       = group_id

        video_name = sanitise_filename(raw_name)
        session_ts = time.strftime("%Y%m%d_%H%M%S")
        log_path   = os.path.join(LOGS_DIR, f"{video_name}_{session_ts}.csv")

        # Security: verify the resolved path stays inside LOGS_DIR
        resolved = os.path.realpath(log_path)
        if not resolved.startswith(os.path.realpath(LOGS_DIR)):
            return f"Security error: invalid log path detected ({log_path})"

        try:
            self._log_file = open(log_path, "w", newline="", encoding="utf-8")
            self._writer   = csv.writer(self._log_file)
            self._writer.writerow(CSV_COLUMNS)
            self._log_file.flush()
            print(f"[LOG] Opened: {log_path}")
            return None  # success
        except Exception as exc:
            return str(exc)

    def close(self) -> None:
        """Flush and close the current log file, if open."""
        if self._log_file and not self._log_file.closed:
            self._log_file.flush()
            self._log_file.close()
            print("[LOG] Closed")
        self._log_file = None
        self._writer   = None

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    @property
    def is_open(self) -> bool:
        """
        Check if a log file is currently open and ready for writing.

        Returns
        -------
        bool
            True if log file is open and writer is available
        """
        return (
            self._log_file is not None
            and not self._log_file.closed
            and self._writer is not None
        )

    def write_row(self, frame_id: int, timestamp_sec: float, track_id,
                  class_name: str, bbox: tuple, centre: tuple,
                  confidence: float, direction: str, event: str,
                  frame_width: int = 0, frame_height: int = 0,
                  speed_px_s: float = 0.0) -> None:
        """
        Write a single detection row to the CSV log file.

        Parameters
        ----------
        frame_id : int
            Current frame number in the video
        timestamp_sec : float
            Elapsed time in seconds since video start
        track_id : int
            Unique identifier for the tracked object
        class_name : str
            Detected object class (car, bus, truck, etc.)
        bbox : tuple
            Bounding box as (x1, y1, x2, y2)
        centre : tuple
            Box center as (cx, cy)
        confidence : float
            Detection confidence score (0.0 – 1.0)
        direction : str
            Movement direction ("up", "down", or "")
        event : str
            Event type: "entry", "exit", or "" (no crossing)
        frame_width : int
            Width of the video frame in pixels
        frame_height : int
            Height of the video frame in pixels
        speed_px_s : float
            Estimated speed of the object in pixels per second
        """
        if not self.is_open:
            return

        x1, y1, x2, y2 = bbox
        cx, cy          = centre

        # crossed_line is True when an entry or exit event occurred
        crossed_line = "true" if event in ("entry", "exit") else "false"

        # direction: use lowercase to match schema ("up"/"down"/"")
        dir_out = direction.lower() if crossed_line == "true" else ""

        self._writer.writerow([
            frame_id, round(timestamp_sec, 3),
            self.scene_name, self.group_id, self.video_basename,
            track_id, class_name, round(confidence, 3),
            x1, y1, x2, y2, cx, cy,
            frame_width, frame_height,
            crossed_line, dir_out, round(speed_px_s, 1),
        ])

    def flush_pending(self, pending_events: dict, frame_id: int,
                      track_classes: dict, track_confidences: dict,
                      track_directions: dict, trajectories: dict,
                      frame_width: int = 0, frame_height: int = 0) -> None:
        """
        Write any crossing events that were detected on unlogged frames.

        This handles the case where a track crosses the counting line
        but wasn't logged in that specific frame (due to skip-frame
        optimization). Called before closing the log to ensure no
        event is lost.

        Parameters
        ----------
        pending_events : dict
            Dictionary of track_id -> list of events that occurred
            but weren't yet written to the log
        frame_id : int
            Current frame number
        track_classes : dict
            Mapping of track_id to class name
        track_confidences : dict
            Mapping of track_id to confidence score
        track_directions : dict
            Mapping of track_id to direction (UP/DOWN/NONE)
        trajectories : dict
            Mapping of track_id to list of (cx, cy) positions
        frame_width : int
            Width of the video frame in pixels
        frame_height : int
            Height of the video frame in pixels
        """
        if not pending_events or not self.is_open:
            return

        # Use elapsed-time placeholder of 0.0 since exact timestamp is unknown
        timestamp_sec = 0.0

        for track_id, event_list in pending_events.items():
            class_name = track_classes.get(track_id, "object")
            confidence = track_confidences.get(track_id, 0.0)
            direction  = track_directions.get(track_id, "")
            pts        = trajectories.get(track_id, [])
            cx, cy     = pts[-1] if pts else (0, 0)

            for event in event_list:
                crossed_line = "true" if event in ("entry", "exit") else "false"
                dir_out      = direction.lower() if crossed_line == "true" else ""

                self._writer.writerow([
                    frame_id, timestamp_sec,
                    self.scene_name, self.group_id, self.video_basename,
                    track_id, class_name, round(confidence, 3),
                    0, 0, 0, 0, cx, cy,
                    frame_width, frame_height,
                    crossed_line, dir_out, 0.0,
                ])
                print(f"[LOG] Flushed pending {event} track={track_id}")

        pending_events.clear()
        self._log_file.flush()

    def periodic_flush(self, frame_id: int, skip_frames: int) -> None:
        """
        Periodically flush the log file to limit data loss on crash.

        Flushes every 20 logged frames to balance performance and
        data safety.

        Parameters
        ----------
        frame_id : int
            Current frame number
        skip_frames : int
            Number of frames between YOLO detections
        """
        if self.is_open and frame_id % (skip_frames * 20) == 0:
            self._log_file.flush()
