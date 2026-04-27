# YOLO Detection and Tracking System

Object Detection, Tracking and Counting with Log Analysis

---

## Project Overview

This project is a desktop application for real-time vehicle and pedestrian detection, tracking and counting using computer vision. It combines a YOLO object detection model with the DeepSORT tracking algorithm to identify, follow and count objects crossing a configurable line in a video. All detection results are saved to CSV log files which can later be imported into the built-in analysis dashboard.

The application is built with Python, PyQt5 for the graphical interface, OpenCV for video processing, Ultralytics YOLO for detection, and DeepSORT Realtime for tracking.

---

## Project Structure

```
project/
    main.py          Application entry point, detection and tracking logic
    ui.py            Graphical interface, live filter, and log analysis panel
    detector.py      YOLO model wrapper
    requirements.txt Python dependencies
    logs/            Auto-created directory for CSV session logs
```

---

## Requirements

Python 3.10 or higher is required.

Install all dependencies with:

```
pip install -r requirements.txt
```

The requirements.txt file contains:

```
opencv-python
PyQt5
ultralytics
deep-sort-realtime
numpy
```

---

## How to Run

```
python main.py
```

---

## How to Use the Application

### Live Detection Tab

1. Click "Select Video File" and choose a video in mp4, avi, mov, mkv or webm format.
2. Use the "Class Filter" checkboxes to select which object categories to detect.
3. Use the "Counting Line Position" slider to place the horizontal counting line at the correct height in the image. This must be done before starting. The line is locked during playback.
4. Click "Start" to begin detection and tracking.
5. Click "Pause" to temporarily suspend playback. Click again to resume.
6. Click "Stop" to end the session. The log file is automatically saved to the logs/ directory.

When the video finishes, a summary screen shows the total objects detected, entries, exits and net flow.

### Log Analysis Tab

1. Click "Add Files" or "Add Folder" to load one or more CSV log files generated during previous sessions.
2. Use the "Class Filter" checkboxes to include or exclude specific classes from the analysis.
3. Click "Run Analysis" to process the loaded files.
4. The dashboard updates with six stat cards, six charts and a detailed data table.
5. Click "Export Filtered CSV" to save the filtered records to a new file.

---

## Detected Classes

The application detects and tracks the following object categories: car, bus, truck, motorcycle, bicycle, person.

---

## Log File Format

Each session produces a CSV file in the logs/ directory named with the sanitised video name and the session timestamp, for example: myvideo_20260426_162819.csv

| Column | Description |
|---|---|
| video | Name of the source video file |
| frame_id | Frame number in the video |
| timestamp | Unix timestamp at time of detection |
| track_id | Unique identifier assigned by DeepSORT |
| class | Detected object class |
| x1, y1, x2, y2 | Bounding box coordinates in pixels |
| width, height | Bounding box dimensions in pixels |
| cx, cy | Centre point of the bounding box |
| confidence | YOLO detection confidence (0 to 1) |
| direction | Dominant movement direction: UP, DOWN or NONE |
| event | Crossing event: entry, exit or none |

---

## Analysis Dashboard

After running analysis the panel provides the following outputs.

Stat Cards show the number of files loaded, unique tracks, frames analysed, total entries, total exits and net flow.

Class Distribution is a bar chart showing the number of unique objects per class. The sum of all bars always equals the total tracks card value.

Traffic Mix is a pie chart showing the percentage share of each class in total traffic.

Direction Split shows how many unique objects moved predominantly upward versus downward.

Position Heatmap is a 22x22 grid showing where objects appeared most frequently in the frame.

Trajectory Map shows the movement paths of all tracked objects colour-coded by class.

Average Confidence shows mean detection confidence per class, averaged first per track then across all tracks of that class.

---

## Counting Logic

An object is counted as an entry when it moves downward and its centre or bottom edge crosses the counting line from above to below.

An object is counted as an exit when it moves upward and its centre or bottom edge crosses the counting line from below to above.

Using the bottom edge in addition to the centre ensures that large objects such as trucks and buses are counted even when their centre never reaches the line.

Each track is counted at most once in each direction per session.

---

## Security Measures

Path traversal prevention: video filenames are sanitised with a regex before being used in log file paths. Only alphanumerics, dots, hyphens and underscores are kept.

Log path verification: the resolved path is checked against LOGS_DIR before any file is opened.

CSV file size limit: files larger than 50 MB are rejected.

CSV structure validation: column names are verified against the expected set before data is read.

Data validation: class, direction and event values are checked against allowed sets. Numeric fields are parsed with bounds-clamping that rejects NaN and Infinity.

Table row cap: the results table displays at most 10 000 rows.

Memory management: expired tracks are pruned from all per-track dictionaries every frame.

Counting line lock: the slider is disabled during playback to prevent phantom crossings.

---

## Known Limitations

Detection confidence is sensitive to video resolution and camera angle.

Objects that pass through the scene without crossing the counting line are tracked but not counted.

Objects visible for too few frames cannot be assigned a direction and therefore cannot trigger a crossing event.
