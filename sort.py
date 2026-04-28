"""
sort.py
~~~~~~~
Simple SORT (Simple Online and Realtime Tracking) implementation.

This is a basic multi-object tracker that assigns unique IDs to
detected objects across consecutive frames. Each detection gets
a new track ID - in production, you'd use a more sophisticated
association algorithm (like Kalman filters or IOU matching).

Note: This is a simplified placeholder. For better tracking,
consider using DeepSORT or ByteTrack.

Dependencies:
    - numpy
"""
import numpy as np


class Sort:
    """
    Simple object tracker that assigns sequential IDs to detections.
    
    This implementation simply assigns a new ID to each detection
    without any actual tracking/association logic. It's primarily
    a placeholder for more sophisticated tracking algorithms.
    
    Attributes
    ----------
    next_id : int
        The next available track ID to assign
    tracks : dict
        Dictionary mapping track_id to bounding box coordinates
    """

    def __init__(self, max_age=10):
        """
        Initialize the SORT tracker.
        
        Parameters
        ----------
        max_age : int, optional
            Maximum number of frames to keep a track alive without
            detection (currently unused in this simple implementation)
        """
        # Track ID counter - increments with each new detection
        self.next_id = 0
        
        # Store track information: track_id -> (x1, y1, x2, y2)
        self.tracks = {}

    def update(self, detections):
        """
        Update tracks with new detections.
        
        Parameters
        ----------
        detections : list or array
            List of detections, each containing [x1, y1, x2, y2, confidence]
            
        Returns
        -------
        results : np.ndarray
            Array of detections with added track IDs:
            [x1, y1, x2, y2, track_id]
        """
        results = []

        # Process each detection
        for det in detections:
            # Extract bounding box coordinates
            x1, y1, x2, y2, _ = det

            # Assign a new unique ID to this detection
            track_id = self.next_id
            
            # Store the bounding box for this track
            self.tracks[track_id] = (x1, y1, x2, y2)

            # Append track ID to the result
            results.append([x1, y1, x2, y2, track_id])

            # Increment ID for next detection
            self.next_id += 1

        return np.array(results)