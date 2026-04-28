"""
detector.py
~~~~~~~~~~~
YOLO object detector wrapper using Ultralytics YOLOv8.

This module provides a simple interface for running YOLO inference
on video frames. It handles model loading, GPU acceleration, and
FPS calculation.

Dependencies:
    - ultralytics (YOLO)
    - opencv-python (cv2)
    - numpy
"""
import time

# YOLO model from Ultralytics
from ultralytics import YOLO


class Detector:
    """
    YOLO-based object detector.
    
    Loads the YOLOv8 nano model (yolov8n.pt) and provides inference
    on individual frames. Automatically attempts GPU acceleration.
    """

    def __init__(self):
        """
        Initialize the detector.
        
        Loads the YOLOv8 nano model and attempts to use CUDA GPU
        for faster inference. Falls back to CPU if GPU is unavailable.
        """
        # Load YOLO model - using nano version for speed
        self.model = YOLO("yolov8n.pt")

        # Attempt to use GPU (CUDA) for inference
        # This will silently fail and continue on CPU if no GPU available
        try:
            self.model.to("cuda")
        except:
            # GPU not available - will use CPU
            pass

        # Track previous frame time for FPS calculation
        self.prev_time = 0

    def detect(self, frame):
        """
        Run object detection on a single frame.
        
        Parameters
        ----------
        frame : np.ndarray
            Input frame in BGR format (as read by OpenCV)
            
        Returns
        -------
        results : list
            YOLO detection results containing bounding boxes,
            confidence scores, and class predictions
        fps : float
            Current frames per second based on processing time
        """
        # Run YOLO inference on the frame
        # conf=0.4: Only keep detections with >40% confidence
        # iou=0.5: Non-maximum suppression threshold
        # verbose=False: Suppress YOLO console output
        results = self.model(frame, conf=0.4, iou=0.5, verbose=False)

        # Calculate FPS based on time since last frame
        current_time = time.time()
        # Avoid division by zero on first frame
        fps = 1 / (current_time - self.prev_time) if self.prev_time else 0
        self.prev_time = current_time

        return results, fps