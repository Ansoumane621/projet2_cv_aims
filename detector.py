import time
from ultralytics import YOLO

class Detector:
    def __init__(self):
        # Load YOLO model
        self.model = YOLO("yolov8n.pt")

        # Use GPU if available
        try:
            self.model.to("cuda")
        except:
            pass

        self.prev_time = 0

    def detect(self, frame):
        # YOLO inference
        results = self.model(frame, conf=0.4, iou=0.5, verbose=False)

        # FPS calculation
        current_time = time.time()
        fps = 1 / (current_time - self.prev_time) if self.prev_time else 0
        self.prev_time = current_time

        return results, fps