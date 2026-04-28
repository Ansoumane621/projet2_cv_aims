"""
app.py
~~~~~~
App — wires the UI to TrackerEngine and SessionManager.

This is the main application controller that orchestrates all components:
- UI (from ui.py) for the graphical interface
- TrackerEngine for YOLO detection + DeepSORT tracking
- SessionManager for CSV logging

Responsibilities
----------------
- Video file selection via file dialog
- Session start / pause / stop lifecycle management
- QTimer-driven frame processing loop
- End-of-video summary display
- Resource cleanup on exit

The App class inherits from UI to get the full interface, then adds
application-specific logic for video playback and session management.
"""
import atexit
import os
import sys
import time

import cv2
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QApplication, QFileDialog

from constants import BASE_DIR, LOGS_DIR, sanitise_filename
from session_manager import SessionManager
from tracker_engine import TrackerEngine
from ui import UI


class App(UI):
    """
    Main application controller.
    
    Inherits from UI to get the full PyQt5 interface, then adds
    video playback, detection session management, and logging.
    """

    def __init__(self):
        """
        Initialize the application.
        
        Sets up core components, configures button connections,
        and prepares the video processing pipeline.
        """
        super().__init__()

        # Debug output - shows paths being used
        print(f"[INIT] BASE_DIR = {BASE_DIR}")
        print(f"[INIT] LOGS_DIR = {LOGS_DIR}")
        print(f"[INIT] CWD      = {os.getcwd()}")

        # Ensure logs directory exists
        os.makedirs(LOGS_DIR, exist_ok=True)

        # ── Core components ───────────────────────────────────────────────
        # TrackerEngine: handles YOLO detection + DeepSORT tracking
        self.engine  = TrackerEngine()
        
        # SessionManager: handles CSV logging
        self.session = SessionManager()

        # ── Video capture ─────────────────────────────────────────────────
        self.cap        = None          # OpenCV VideoCapture object
        self.video_path = None          # Path to selected video file
        self.out        = None          # OpenCV VideoWriter for output

        # ── Counting line (locked at session start) ────────────────────────
        # The y-position of the counting line is locked when session starts
        # to prevent changing it mid-video (which would invalidate counts)
        self._session_line_y = 240

        # ── Timer for frame processing ─────────────────────────────────────
        # QTimer fires every 25ms to process the next frame
        # This gives us ~40 FPS maximum display rate
        self.timer = QTimer()
        self.timer.timeout.connect(self._update_frame)

        # ── Button wiring ─────────────────────────────────────────────────
        # Connect UI buttons to their handler methods
        self.start_btn.clicked.connect(self.start)
        self.stop_btn.clicked.connect(self.stop)
        self.pause_btn.clicked.connect(self.pause)
        self.select_btn.clicked.connect(self.select_video)

        # ── Populate class selection combo ────────────────────────────────
        # Add "ALL" option first, then add available YOLO classes
        self.class_select.addItem("ALL")
        for name in self.engine.detector.model.names.values():
            # Only add classes we care about for traffic monitoring
            if name in ["car", "bus", "truck", "motorcycle", "bicycle", "person"]:
                self.class_select.addItem(name)

        # ── Cleanup on exit ────────────────────────────────────────────────
        # Ensure resources are released when Python exits
        atexit.register(self._release_resources)

    # =========================================================================
    # VIDEO SELECTION
    # =========================================================================

    def select_video(self):
        """
        Open a file dialog to select a video file.
        
        Updates the video path label and prepares the VideoCapture
        object for playback.
        """
        # Open native file dialog
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
    # START / PAUSE / STOP
    # =========================================================================

    def start(self):
        """
        Start video processing session.
        
        This method:
        1. Validates that a video is selected and can be opened
        2. Resets the video to frame 0
        3. Creates an output video writer
        4. Locks the counting line position
        5. Resets the tracker engine
        6. Opens a new CSV log file
        7. Starts the frame processing timer
        """
        print("[START] Start button clicked")

        # Validate video is selected
        if self.cap is None:
            self._set_warning("Warning: Select a video first!"); return
        if not self.cap.isOpened():
            self._set_warning("Warning: Could not open video file."); return

        # Reset video to beginning
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

        # Create output video writer (saves annotated video)
        fps    = int(self.cap.get(cv2.CAP_PROP_FPS)) or 30  # Default to 30 if unknown
        fourcc = cv2.VideoWriter_fourcc(*"XVID")             # XVID codec for AVI
        out_path = os.path.join(BASE_DIR, f"output_{int(time.time())}.avi")
        self.out = cv2.VideoWriter(out_path, fourcc, fps, (640, 480))
        print(f"[START] Output video: {out_path}")

        # Lock counting line - don't allow changes during session
        self._session_line_y = self.get_line_y()
        self.line_slider.setEnabled(False)
        print(f"[START] Counting line locked at y={self._session_line_y}")

        # Reset tracker state for fresh session
        self.engine.reset()
        self.set_live_counts(0, 0)

        # Open CSV log file for this session
        err = self.session.open(self.video_path)
        if err:
            self._set_warning(f"Could not open log file: {err}")
            print(f"[START] ERROR opening log: {err}")
            self.line_slider.setEnabled(True)
            return

        # Start the frame processing timer (25ms = ~40 FPS max)
        self.timer.start(25)
        print("[START] Timer started")

    def pause(self):
        """
        Toggle between paused and running states.
        
        When paused, the timer stops and no new frames are processed.
        When resumed, the timer restarts and processing continues.
        """
        if self.timer.isActive():
            self.timer.stop(); print("[PAUSE] Paused")
        else:
            self.timer.start(25); print("[PAUSE] Resumed")

    def stop(self):
        """
        Stop the current session and clean up resources.
        
        This is called when the user clicks the Stop button.
        It flushes pending events, closes the log file, and
        releases the video writer.
        """
        print("[STOP] Stop requested")
        self.timer.stop()
        self._flush_and_close()
        self._on_video_finished()

    def closeEvent(self, event):
        """
        Handle window close event.
        
        Ensures all resources are properly released when the
        application window is closed.
        """
        print("[CLOSE] Window closing")
        self.timer.stop()
        self._flush_and_close()
        super().closeEvent(event)

    # =========================================================================
    # MAIN PROCESSING LOOP
    # =========================================================================

    def _update_frame(self):
        """
        Process one frame from the video.
        
        This is the main loop - it's called by the QTimer every 25ms.
        It:
        1. Reads the next frame from the video
        2. Runs YOLO + DeepSORT detection/tracking
        3. Writes the annotated frame to output video
        4. Displays the frame in the UI
        5. Updates statistics labels
        """
        if self.cap is None:
            return

        # Read next frame from video
        ret, frame = self.cap.read()
        
        # Check if video ended
        if not ret:
            print(f"[FRAME] End of video at frame {self.engine.frame_id}")
            self.timer.stop()
            self._flush_and_close()
            self._on_video_finished()
            return

        # Process frame through detection + tracking pipeline
        annotated, fps_val, total = self.engine.process_frame(
            frame,
            self._session_line_y,
            self.get_live_allowed_classes(),
            self.session,
        )

        # Write annotated frame to output video
        if self.out:
            self.out.write(annotated)

        # Convert BGR (OpenCV) to RGB (Qt display)
        rgb    = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
        h, w, c = rgb.shape
        img    = QImage(rgb.data, w, h, c * w, QImage.Format_RGB888)
        self.video.setPixmap(QPixmap.fromImage(img))

        # Update UI labels with current stats
        self.counter_label.setText(f"Objects: {total}")
        self.fps_label.setText(
            f"Frame: {self.engine.frame_id}  |  FPS: {fps_val:.1f}"
        )
        
        # Update live count displays
        self.set_live_counts(self.engine.enter_count, self.engine.exit_count)

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _flush_and_close(self):
        """
        Flush pending events and close all output files.
        
        This ensures no detection events are lost when stopping
        and all file handles are properly closed.
        """
        # Flush any events that occurred on frames we skipped
        self.session.flush_pending(
            self.engine.pending_events,
            self.engine.frame_id,
            self.engine.track_classes,
            self.engine.track_confidences,
            self.engine.track_directions,
            self.engine.trajectories,
        )
        self._release_resources()

    def _release_resources(self):
        """
        Release video writer and close session.
        
        Called when session ends or application exits.
        """
        if self.out:
            self.out.release(); self.out = None
            print("[RELEASE] VideoWriter released")
        
        # Close CSV log file
        self.session.close()
        
        # Re-enable the counting line slider
        self.line_slider.setEnabled(True)

    def _set_warning(self, msg: str):
        """
        Display a warning message in the video path label.
        
        Parameters
        ----------
        msg : str
            Warning message to display
        """
        self.video_path_label.setText(f"⚠  {msg}")
        self.video_path_label.setStyleSheet(
            "color:#dc2626;font-size:11px;"
            "background:#fef2f2;border:1px solid #fecaca;"
            "border-radius:6px;padding:6px 10px;"
        )

    def _on_video_finished(self):
        """
        Display summary when video processing completes.
        
        Shows a summary of the session including:
        - Total frames processed
        - Unique objects detected
        - Entry/exit counts
        - Net flow
        """
        # Update live counts one final time
        self.set_live_counts(self.engine.enter_count, self.engine.exit_count)
        
        # Count unique tracks
        total_objects = len(self.engine.track_classes)
        
        # Build summary text
        summary = (
            f"  Video finished\n\n"
            f"  Frames processed : {self.engine.frame_id}\n"
            f"  Unique objects   : {total_objects}\n"
            f"  Entries  (IN)    : {self.engine.enter_count}\n"
            f"  Exits    (OUT)   : {self.engine.exit_count}\n"
            f"  Net flow (NET)   : "
            f"{self.engine.enter_count - self.engine.exit_count:+d}"
        )
        
        # Display summary in video area
        self.video.setText(summary)
        self.video.setStyleSheet(
            "QLabel#video_label{"
            "background:#0f172a;color:#94a3b8;"
            "font-size:14px;font-family:'Courier New';"
            "padding:30px;border-radius:10px;}"
        )
        
        # Update path label with success message
        raw_name   = (os.path.splitext(os.path.basename(self.video_path))[0]
                      if self.video_path else "unknown")
        video_name = sanitise_filename(raw_name)
        self.video_path_label.setText(
            f"✓  Finished — log saved to logs/{video_name}_*.csv"
        )
        self.video_path_label.setStyleSheet(
            "color:#16a34a;font-size:11px;"
            "background:#f0fdf4;border:1px solid #bbf7d0;"
            "border-radius:6px;padding:6px 10px;"
        )
        
        # Print summary to console
        print(
            f"[DONE] IN={self.engine.enter_count} "
            f"OUT={self.engine.exit_count} "
        )
            f"NET={self.engine.enter_count - self.engine.exit_count:+d} "
            f"OBJECTS={total_objects}"
        )


# =============================================================================
# ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication
    _app    = QApplication(sys.argv)
    _window = App()
    _window.show()
    sys.exit(_app.exec_())
