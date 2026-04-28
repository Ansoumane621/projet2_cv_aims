"""
session_manager.py
~~~~~~~~~~~~~~~~~~
Manages a single detection session:
  - opens / closes the CSV log file
  - writes rows (including pending events from unlogged frames)
  - flushes on stop / end-of-video

This module has NO PyQt5 dependency — it is pure Python I/O logic.
"""
import csv
import os
import time
from typing import Optional

from constants import LOGS_DIR, sanitise_filename

# CSV column order (must match the header written at session start)
CSV_COLUMNS = [
    "video", "frame_id", "timestamp",
    "track_id", "class",
    "x1", "y1", "x2", "y2",
    "width", "height", "cx", "cy",
    "confidence", "direction", "event",
]


class SessionManager:
    """Opens, writes to, and closes the CSV log for one detection session."""

    def __init__(self) -> None:
        os.makedirs(LOGS_DIR, exist_ok=True)
        self._log_file: Optional[object] = None
        self._writer:   Optional[csv.writer] = None
        self.video_basename: str = "unknown"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self, video_path: Optional[str]) -> Optional[str]:
        """
        Create a new session log file.

        Returns the log path on success, or an error message string on
        failure (caller should treat a non-None return as an error).
        """
        self.close()   # always close any existing log first

        raw_name = (
            os.path.splitext(os.path.basename(video_path))[0]
            if video_path else "unknown"
        )
        self.video_basename = os.path.basename(video_path) if video_path else "unknown"
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
            return None   # success
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

    def write_row(self, frame_id: int, timestamp: float, track_id,
                  class_name: str, bbox: tuple, dims: tuple, centre: tuple,
                  confidence: float, direction: str, event: str) -> None:
        """
        Write a single detection row to the CSV log file.
        
        Parameters
        ----------
        frame_id : int
            Current frame number in the video
        timestamp : float
            Unix timestamp when the detection occurred
        track_id : int
            Unique identifier for the tracked object
        class_name : str
            Detected object class (car, bus, truck, etc.)
        bbox : tuple
            Bounding box as (x1, y1, x2, y2)
        dims : tuple
            Box dimensions as (width, height)
        centre : tuple
            Box center as (cx, cy)
        confidence : float
            Detection confidence score (0-1)
        direction : str
            Movement direction (UP, DOWN, or NONE)
        event : str
            Event type (entry, exit, or none)
        """
        if not self.is_open:
            return
        l, top, r, b = bbox
        w, h         = dims
        cx, cy       = centre
        self._writer.writerow([
            self.video_basename, frame_id, timestamp,
            track_id, class_name,
            l, top, r, b, w, h, cx, cy,
            confidence, direction, event,
        ])

    def flush_pending(self, pending_events: dict, frame_id: int,
                      track_classes: dict, track_confidences: dict,
                      track_directions: dict, trajectories: dict) -> None:
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
        """
        if not pending_events or not self.is_open:
            return

        timestamp = round(time.time(), 4)
        for track_id, event_list in pending_events.items():
            class_name = track_classes.get(track_id, "object")
            confidence = track_confidences.get(track_id, 0.0)
            direction  = track_directions.get(track_id, "NONE")
            pts        = trajectories.get(track_id, [])
            cx, cy     = pts[-1] if pts else (0, 0)

            for event in event_list:
                self._writer.writerow([
                    self.video_basename, frame_id, timestamp,
                    track_id, class_name,
                    0, 0, 0, 0, 0, 0, cx, cy,
                    confidence, direction, event,
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
