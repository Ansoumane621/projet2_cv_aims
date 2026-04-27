import numpy as np

class Sort:
    def __init__(self, max_age=10):
        self.next_id = 0
        self.tracks = {}

    def update(self, detections):
        results = []

        for det in detections:
            x1, y1, x2, y2, _ = det

            # assign new ID
            track_id = self.next_id
            self.tracks[track_id] = (x1, y1, x2, y2)

            results.append([x1, y1, x2, y2, track_id])

            self.next_id += 1

        return np.array(results)