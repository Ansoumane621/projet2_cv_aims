# YOLO Object Detection, Tracking & Counting System

A desktop application for real-time vehicle and pedestrian detection, tracking, and counting in video files, with a built-in log analysis dashboard.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture & Design Decisions](#2-architecture--design-decisions)
3. [File Structure](#3-file-structure)
4. [How Each Module Works](#4-how-each-module-works)
5. [The Detection & Tracking Pipeline](#5-the-detection--tracking-pipeline)
6. [The Counting Logic](#6-the-counting-logic)
7. [Security Measures](#7-security-measures)
8. [The Analysis Dashboard](#8-the-analysis-dashboard)
9. [Installation & Running](#9-installation--running)
10. [How to Use the Application](#10-how-to-use-the-application)
11. [Log File Format](#11-log-file-format)
12. [Known Limitations](#12-known-limitations)

---

## 1. Project Overview

This project addresses a common real-world problem in traffic monitoring: **automatically counting vehicles and pedestrians crossing a defined line in a video**, without manual annotation.

The application processes a video file frame by frame. For each frame, it:
- Detects objects using a **YOLOv8** neural network
- Assigns persistent identities to each object using **DeepSORT** tracking
- Detects when a tracked object crosses a user-defined horizontal line
- Logs every detection to a **CSV file**
- Provides a separate **analysis dashboard** to visualise results from past sessions

The GUI is built with **PyQt5** and runs as a standard desktop application on Windows, macOS and Linux.

---

## 2. Architecture & Design Decisions

The project was refactored from two large monolithic files (`main.py` at ~700 lines, `ui.py` at ~1160 lines) into a clean modular architecture following the **Single Responsibility Principle**: each module does exactly one thing.

### Separation of concerns

| Layer | Responsibility |
|---|---|
| **UI layer** (`ui.py`, `live_panel.py`, `analysis_panel.py`) | What the user sees — layout, buttons, widgets |
| **Controller layer** (`app.py`) | Wires the UI to the engine — handles button clicks, the QTimer loop |
| **Engine layer** (`tracker_engine.py`) | Pure computer vision logic — YOLO, DeepSORT, counting, annotation |
| **I/O layer** (`session_manager.py`) | CSV file lifecycle — open, write, flush, close |
| **Shared layer** (`constants.py`) | All constants and security helpers used across modules |

### Key design choices

**`tracker_engine.py` has zero PyQt5 dependency.** It takes a NumPy frame as input and returns an annotated NumPy frame. This makes it testable in isolation and reusable outside a GUI context.

**`session_manager.py` has zero PyQt5 dependency.** It is pure Python file I/O. This means the CSV logging logic can be tested and understood independently of the interface.

**`app.py` is the only file that knows both the UI and the engine.** It is the glue layer. If the UI framework were changed from PyQt5 to something else, only `app.py` and the UI files would need to change — the engine and session manager would be untouched.

---

## 3. File Structure

```
project/
│
├── main.py               Entry point — starts the Qt application (13 lines)
├── app.py                Controller — wires UI ↔ engine ↔ session
├── ui.py                 UI shell — title bar + tab widget
│
├── live_panel.py         "Live Detection" tab — video display + controls sidebar
├── analysis_panel.py     "Log Analysis" tab — file picker, charts, data table
│
├── charts.py             Custom QPainter widgets: bar chart, pie chart, heatmap, trajectories
├── stat_card.py          StatCard KPI widget + chart_card helper
│
├── tracker_engine.py     YOLO inference + DeepSORT tracking + counting logic
├── session_manager.py    CSV log file lifecycle (open / write / flush / close)
├── constants.py          Shared constants + security helper functions
│
├── detector.py           Thin wrapper around the Ultralytics YOLO model
├── sort.py               Minimal SORT tracker stub (not used by default)
│
├── style.qss             Qt stylesheet (visual theme)
├── yolov8n.pt            Pre-trained YOLOv8 nano model weights
├── requirements.txt      Python dependencies
└── logs/                 Auto-created — stores CSV session logs
```

---

## 4. How Each Module Works

### `main.py` — Entry point
Creates the `QApplication`, instantiates `App`, shows the window, and starts the Qt event loop. Deliberately kept at 13 lines so that the entry point is always trivially understandable.

### `constants.py` — Shared definitions
Defines every constant used across the project in one place: allowed object classes, colour palettes for the UI and for OpenCV, CSV validation sets, security limits, and helper functions (`safe_float`, `sanitise_filename`, `sanitise_cell`). Having a single source of truth prevents inconsistencies between modules.

### `detector.py` — YOLO wrapper
Loads the YOLOv8 nano model on startup, moves it to GPU if one is available, and exposes a single `detect(frame)` method that returns raw YOLO results plus a real-time FPS measurement.

### `session_manager.py` — CSV log lifecycle
Manages one log file per detection session. Responsibilities:
- **`open(video_path)`** — sanitises the filename, builds a safe path inside `logs/`, verifies it with `os.path.realpath`, creates the file, writes the CSV header
- **`write_row(...)`** — writes one detection row
- **`flush_pending(...)`** — writes any crossing events that were detected on non-logged frames before the file is closed
- **`close()`** — flushes and closes the file safely

### `tracker_engine.py` — Computer vision core
The most important module. Contains all detection, tracking, and counting logic. Exposes one public method:

```python
annotated, fps, total = engine.process_frame(frame, line_y, allowed_classes, session)
```

Internally it runs the full pipeline described in Section 5.

### `app.py` — Controller
Inherits from `UI` and connects everything together:
- Button signals → `start()`, `pause()`, `stop()`, `select_video()`
- A `QTimer` fires every 25 ms and calls `engine.process_frame()`
- The returned annotated frame is converted from BGR to RGB and displayed in the `QLabel` video widget
- At end-of-video or on stop, it calls `session.flush_pending()` then `session.close()`

### `ui.py` — UI shell
Builds the title bar and the two-tab `QTabWidget`. Uses Python's `__getattr__` to transparently delegate attribute access to `LivePanel`, so that `app.py` can write `self.video` or `self.start_btn` without needing to know which sub-widget they live in.

### `live_panel.py` — Live Detection tab
Builds the left video display and the right controls sidebar: video source selector, class filter checkboxes, playback controls, live IN/OUT/NET counters, counting line slider, and events log.

### `analysis_panel.py` — Log Analysis tab
Handles the entire analysis workflow: file validation, CSV parsing, data aggregation by unique track, updating 6 stat cards, 6 charts, and a scrollable data table. The analysis runs synchronously on the main thread (acceptable for typical log sizes up to 50 MB).

### `charts.py` — Custom chart widgets
Four widgets drawn with `QPainter` (Qt's low-level 2D drawing API), requiring no external charting library:
- **`MiniBarChart`** — gradient vertical bars with a grid and Y-axis scale
- **`MiniPieChart`** — proportional sectors with a legend showing percentages
- **`HeatmapWidget`** — 22×22 grid coloured from blue (low density) to green (high density)
- **`TrajectoryCanvas`** — object movement paths on a dark background, colour-coded by class

### `stat_card.py` — KPI card widget
A reusable `QFrame` subclass that displays an icon, a label, and a large numeric value. Six colour themes (blue, green, red, amber, purple, slate) are defined as tuples of background / border / text / accent colours.

---

## 5. The Detection & Tracking Pipeline

Every 25 ms the `QTimer` triggers `_update_frame()` in `app.py`, which calls `engine.process_frame()`. Inside the engine, the following steps run in sequence:

```
Frame N arrives (NumPy BGR image)
        │
        ▼
  Resize to 640×480
        │
        ├─ Frame N % 2 == 0 ? ──YES──► Run YOLOv8 inference
        │                               Filter by class + confidence (≥ 0.4)
        │                               Filter by user's class checkbox selection
        │                               Store detections as (bbox, conf, class)
        │
        └─ Frame N % 2 == 1 ? ──YES──► Reuse detections from frame N-1
                                        (saves ~50% of GPU/CPU time)
        │
        ▼
  DeepSORT.update_tracks(detections, frame)
  → assigns persistent track_id to each bounding box
  → uses Kalman filter to predict position on non-detection frames
        │
        ▼
  For each confirmed track:
    ├── Persist class name and confidence score
    ├── Append (cx, cy) to trajectory buffer (max 20 points)
    ├── Compute movement direction (UP / DOWN) from Δcy vs. previous frame
    ├── Check for counting-line crossing (see Section 6)
    ├── Write row to CSV log (every 2nd frame)
    └── Draw bounding box, label, and trajectory tail on the frame
        │
        ▼
  Draw counting line + IN/OUT/NET overlay
        │
        ▼
  Return annotated frame → displayed in QLabel
```

**Why skip every other frame for YOLO?**
YOLOv8 nano inference takes ~30–80 ms per frame depending on hardware. Running it on every frame would cap the display at 12–33 FPS. By running YOLO every 2 frames and letting DeepSORT's Kalman filter interpolate positions on the skipped frames, the display remains smooth at ~40 FPS while detection accuracy is barely affected, because objects do not move significantly in one frame.

---

## 6. The Counting Logic

A horizontal counting line is placed by the user before starting a session. Its Y coordinate is **locked** at session start and cannot change during playback.

An object is counted **once per direction per session**:

```
Entry (DOWN crossing):
  direction == "DOWN"
  AND (prev_cy < line_y AND cy >= line_y)   ← centre crossed
  OR  (prev_bottom < line_y AND b >= line_y) ← bottom edge crossed

Exit (UP crossing):
  direction == "UP"
  AND (prev_cy > line_y AND cy <= line_y)
  OR  (prev_bottom > line_y AND b <= line_y)
```

**Why check the bottom edge in addition to the centre?**
Large objects like trucks and buses can have a bounding box tall enough that their centre never reaches the counting line, even though the vehicle physically crosses it. Checking the bottom edge ensures these objects are always counted.

**Why use `prev_cy` from the immediately previous frame?**
An earlier version used the trajectory buffer (updated every 2 frames) as the previous position. This introduced a 2-frame lag in crossing detection and caused fast-moving objects to be missed entirely. The current implementation maintains `prev_cy_map` and `prev_bottom_map` updated on every single frame, giving pixel-perfect crossing detection regardless of object speed.

**Pending events buffer**
The CSV log is written every 2 frames (aligned with YOLO inference). A crossing detected on an odd (non-logged) frame would be silently lost. To prevent this, crossing events are first placed in a `pending_events` dict. On the next logged frame, all pending events are drained to the CSV before the normal row is written. When the session ends, any remaining pending events are flushed by `session_manager.flush_pending()`.

---

## 7. Security Measures

Several security and robustness measures are built into the application.

**Path traversal prevention** — Before a video filename is used to build a log path, it is sanitised with a regex that removes every character that is not alphanumeric, a dot, a hyphen, or an underscore. The resolved path is then verified with `os.path.realpath()` to confirm it stays inside the `logs/` directory. A filename like `../../etc/passwd.mp4` is reduced to `______etc_passwd.mp4` and would then be blocked by the path check.

**CSV structure validation** — When loading a CSV for analysis, the column names are checked against the expected set before any data is read. Files with missing or unexpected columns are rejected with a clear error message.

**CSV file size limit** — Files larger than 50 MB are rejected at load time to prevent memory exhaustion.

**Data validation** — The `class`, `direction`, and `event` columns are validated against known allowed sets. Numeric columns (`cx`, `cy`, `confidence`) are parsed through `safe_float()` which clamps the value to a valid range and rejects NaN and Infinity.

**Memory management** — The per-track state dictionaries (`trajectories`, `track_classes`, etc.) are pruned every frame by removing entries for tracks that DeepSORT no longer reports as active. Without this, long videos with thousands of objects would cause unbounded RAM growth. A hard cap of 1000 entries on `track_counted` provides a final safety net.

**Counting line lock** — The counting line slider is disabled as soon as a session starts. Moving the line during playback would cause objects that were above the line to suddenly be "below" it, generating phantom crossing events. The locked `_session_line_y` value is used exclusively during the session; the slider's live value is ignored.

**DeepSORT reinitialisation** — DeepSORT keeps internal state (Kalman filters, track IDs) between sessions. Without reinitialisation, track IDs from a previous run could be reused in a new session, allowing an already-counted track to bypass the duplicate-counting guard. A fresh `DeepSort` instance is created at the start of every session.

**Table row cap** — The results table displays at most 10,000 rows regardless of how many records are in the CSV, preventing the UI from freezing on very large files.

---

## 8. The Analysis Dashboard

The Log Analysis tab allows importing one or more CSV log files from previous sessions and visualising the aggregated results.

**Stat cards** show: number of files loaded, unique tracked objects, frames analysed, total entry events, total exit events, and net flow (entries − exits).

**Class Distribution** — bar chart showing how many unique objects were detected per class (car, bus, truck, etc.).

**Traffic Mix** — pie chart showing each class as a percentage of total traffic.

**Direction Split** — bar chart showing how many objects moved predominantly upward versus downward across all files.

**Position Heatmap** — a 22×22 grid mapped to the 640×480 frame coordinate space. Each cell is coloured according to how many detections occurred in that area: blue for sparse, cyan for moderate, green for dense. Shows where in the scene objects spend the most time.

**Trajectory Map** — draws the movement paths of every tracked object on a dark background, colour-coded by class, with opacity increasing toward the end of each path to show direction of travel.

**Average Confidence** — bar chart showing mean YOLO detection confidence per class, averaged first across frames within each track, then across all tracks of the same class. Gives an indication of how reliably each class is detected.

---

## 9. Installation & Running

**Requirements:** Python 3.10 or higher, pip.

```bash
pip install -r requirements.txt
pip install PyQt5
```

The `requirements.txt` contains:

```
ultralytics==8.3.145
deep-sort-realtime==1.3.2
opencv-python-headless==4.10.0.84
numpy==1.26.4
```

**Run the application:**

```bash
python main.py
```

The model file `yolov8n.pt` must be in the same directory as `main.py`. It is downloaded automatically by Ultralytics on first run if not present.

---

## 10. How to Use the Application

### Live Detection tab

1. Click **Select Video File** and choose a video (`.mp4`, `.avi`, `.mov`, `.mkv`, `.webm`).
2. Use the **Class Filter** checkboxes to select which object types to detect. All classes are enabled by default.
3. Drag the **Counting Line Position** slider to set the horizontal line height. The percentage label updates in real time. This must be done before clicking Start.
4. Click **Start**. The slider locks and detection begins.
5. Click **Pause** to freeze playback. Click again to resume.
6. Click **Stop** to end the session early. The log is saved automatically.

When the video ends naturally, a summary screen shows total frames processed, unique objects, entries, exits, and net flow. The log file path is shown in the status label.

### Log Analysis tab

1. Click **Add Files** to select one or more CSV log files, or **Add Folder** to load all CSV files from a directory.
2. Use the **Class Filter** checkboxes to include or exclude specific classes from the analysis.
3. Click **Run Analysis**. The progress bar advances as each file is processed.
4. Review the stat cards, charts, and data table.
5. Click **Export Filtered CSV** to save the filtered records to a new file.

---

## 11. Log File Format

Each session creates a CSV file in the `logs/` directory named `<video>_<timestamp>.csv`, for example `highway_20260426_162819.csv`.

| Column | Type | Description |
|---|---|---|
| `video` | string | Source video filename |
| `frame_id` | integer | Frame number in the video |
| `timestamp` | float | Unix timestamp at detection time |
| `track_id` | integer | Persistent ID assigned by DeepSORT |
| `class` | string | Detected class: car, bus, truck, motorcycle, bicycle, person |
| `x1`, `y1` | integer | Top-left corner of bounding box (pixels) |
| `x2`, `y2` | integer | Bottom-right corner of bounding box (pixels) |
| `width`, `height` | integer | Bounding box dimensions (pixels) |
| `cx`, `cy` | integer | Centre point of bounding box (pixels) |
| `confidence` | float | YOLO detection confidence, 0 to 1 |
| `direction` | string | Dominant movement direction: UP, DOWN, or NONE |
| `event` | string | Crossing event: entry, exit, or none |

Rows are written every 2 frames (aligned with YOLO inference). Crossing events detected on non-logged frames are written on the next logged frame via the pending events buffer.

---

## 12. Known Limitations

**Confidence sensitivity** — Detection accuracy depends heavily on video resolution, camera angle, and lighting. Low-resolution or heavily compressed videos will produce more false positives and missed detections.

**Objects that never cross the line** — Objects that enter and leave the frame without crossing the counting line are tracked and logged but are never assigned an entry or exit event.

**Short tracks** — Objects visible for only 1–2 frames may not accumulate enough direction history to trigger a crossing event, even if they physically cross the line.

**Single-threaded processing** — YOLO inference and the Qt GUI run on the same thread. On slow hardware this may cause the UI to feel unresponsive during heavy scenes. A future improvement would be to run the engine in a `QThread`.

**Fixed output resolution** — All video is resized to 640×480 before processing. Very high-resolution input videos lose detail that could improve detection accuracy for small or distant objects.

---

## 13. Deploying on Hugging Face Spaces — Limitations & Requirements

This section explains what would be needed to deploy this project on Hugging Face Spaces, and why it cannot be done as-is.

### Why the current application cannot run on Hugging Face Spaces

Hugging Face Spaces runs applications inside a **headless Linux container** — a server with no screen, no display, and no desktop environment. This project is built around **PyQt5**, which is a desktop GUI framework that requires a physical or virtual display to render windows. On Hugging Face, PyQt5 would crash immediately with an error like `cannot connect to X server` because there is no graphical environment available.

Additionally, Hugging Face Spaces is designed for **web applications** accessible from a browser, not for native desktop applications that open a local window.

### What would need to change

To deploy this project on Hugging Face Spaces, the entire interface layer would need to be replaced with a **web-based UI framework**. The two standard options for Python ML applications are:

**Option A — Gradio** (simplest, recommended for demos)

Gradio is Hugging Face's own recommended framework. It generates a web interface automatically from Python functions. The deployment would work roughly as follows:

- Replace `PyQt5`, `live_panel.py`, `ui.py`, `app.py`, `stat_card.py` with a Gradio app
- Keep `tracker_engine.py`, `session_manager.py`, `constants.py`, and `detector.py` entirely unchanged — they have no GUI dependency
- The Gradio interface would accept a video file upload, run `tracker_engine.process_frame()` on each frame, and return the annotated video as output
- The analysis dashboard charts would need to be regenerated using `matplotlib` or `plotly` instead of custom `QPainter` widgets
- Note: `gradio` is already listed as a dependency in the original `requirements.txt`, which suggests this deployment was considered from the start

A minimal `app.py` for Gradio would look like this:

```python
import gradio as gr
from tracker_engine import TrackerEngine

def process_video(video_path, line_y):
    engine = TrackerEngine()
    # process frames and return annotated video
    ...

demo = gr.Interface(fn=process_video, inputs=["video", "slider"], outputs="video")
demo.launch()
```

**Option B — Streamlit** (more control over layout)

Streamlit is another popular Python web framework. It offers more layout flexibility than Gradio but requires more code. The same principle applies: keep the engine, replace the GUI layer.

### Hardware constraints on Hugging Face Spaces

| Resource | Free tier | Paid tier |
|---|---|---|
| CPU | 2 vCPUs | Up to 8 vCPUs |
| RAM | 16 GB | Up to 32 GB |
| GPU | ❌ Not available | T4 (16 GB VRAM) |
| Storage | Temporary only | Temporary only |
| Timeout | 48h inactivity restart | 48h inactivity restart |

**GPU availability** is the most important constraint. This project uses YOLOv8 and DeepSORT, which both benefit significantly from a GPU. On the free tier (CPU only), processing a 30 FPS video in real time would be impossible — inference alone takes ~200–400 ms per frame on CPU, meaning the maximum throughput would be around 2–5 FPS. On a paid T4 GPU Space, real-time processing at 25–30 FPS becomes achievable.

**Storage is temporary** — Hugging Face Spaces does not provide persistent storage. The `logs/` directory and all CSV files written during a session would be deleted when the container restarts. To persist session logs, an external storage solution would be required, such as the Hugging Face Dataset Hub (via the `huggingface_hub` library) or an external database.

### Summary table

| What to keep | What to replace | What to add |
|---|---|---|
| `tracker_engine.py` | `ui.py` | `gradio` or `streamlit` |
| `session_manager.py` | `live_panel.py` | `matplotlib` or `plotly` for charts |
| `constants.py` | `analysis_panel.py` | External storage for CSV logs |
| `detector.py` | `app.py` | `spaces` GPU decorator (optional) |
| `detector.py` | `charts.py` (QPainter) | |
| `yolov8n.pt` | `stat_card.py` | |
| `requirements.txt` (partial) | `style.qss` | |
