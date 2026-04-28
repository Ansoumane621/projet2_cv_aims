"""
main.py
~~~~~~~
Application entry point.

This is the single point of entry for the YOLO Tracker application.
It creates the QApplication instance and the main App window,
then starts the Qt event loop.

Usage:
    python main.py

The application requires:
    - PyQt5 for the GUI
    - OpenCV (cv2) for video processing
    - YOLO model (yolov8n.pt) in the same directory
    - Python 3.8+

No command-line arguments are supported - all configuration
is done through the GUI.
"""
import sys

# PyQt5 widgets module
from PyQt5.QtWidgets import QApplication

# Main application window
from app import App


# Create Qt application instance
# This must be done before creating any widgets
app    = QApplication(sys.argv)

# Create and show the main window
window = App()
window.show()

# Start the Qt event loop
# sys.exit() ensures proper cleanup on exit
sys.exit(app.exec_())
