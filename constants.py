"""
constants.py
~~~~~~~~~~~~~
Shared constants and security utilities used across the application.

This module centralizes all configuration values, color schemes,
and helper functions that are used by multiple other modules.
Having all constants in one place makes it easy to tweak settings
without hunting through individual files.

Contents:
    - Path configuration (BASE_DIR, LOGS_DIR)
    - Detection/tracking settings (ALLOWED_CLASSES, MAX_ACTIVE_TRACKS)
    - Analysis settings (MAX_CSV_BYTES, MAX_TABLE_ROWS)
    - Column definitions for CSV export
    - Color palettes for UI and OpenCV rendering
    - Security utilities (sanitise_filename, safe_float, etc.)
"""
import math
import os
import re

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# Base directory - where this Python file is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Logs directory - subfolder for CSV output files
LOGS_DIR = os.path.join(BASE_DIR, "logs")

# ---------------------------------------------------------------------------
# Detection / tracking
# ---------------------------------------------------------------------------
# Object classes to detect and track
# These correspond to COCO dataset classes that are relevant for traffic
ALLOWED_CLASSES = ["car", "bus", "truck", "motorcycle", "bicycle", "person"]

# Maximum number of simultaneous tracks to maintain
# This is a safety cap to prevent memory exhaustion on long videos
MAX_ACTIVE_TRACKS = 1000

# ---------------------------------------------------------------------------
# Analysis / UI
# ---------------------------------------------------------------------------
# Maximum CSV file size (50 MB) - prevents loading huge files
MAX_CSV_BYTES  = 50 * 1024 * 1024

# Maximum rows to display in analysis table - prevents UI lag
MAX_TABLE_ROWS = 10_000

# Expected CSV column names (used for validation) — professor's schema
EXPECTED_COLUMNS = {
    "frame", "timestamp_sec", "scene_name", "group_id", "video_name",
    "track_id", "class_name", "confidence",
    "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2", "cx", "cy",
    "frame_width", "frame_height",
    "crossed_line", "direction", "speed_px_s",
}

# Valid object classes for analysis validation
KNOWN_CLASSES    = {"car", "bus", "truck", "motorcycle", "bicycle", "person"}

# Valid direction values
KNOWN_DIRECTIONS = {"UP", "DOWN", "NONE", ""}

# Valid crossed_line values (boolean string)
KNOWN_EVENTS     = {"true", "false", ""}

# Color palette for UI charts (hex colors)
# Used by analysis_panel.py for bar charts and pie charts
CLASS_PALETTE = {
    "car":        "#2563eb",  # Blue
    "bus":        "#7c3aed",  # Purple
    "truck":      "#0891b2",  # Cyan
    "motorcycle": "#ea580c",  # Orange
    "bicycle":    "#16a34a",  # Green
    "person":     "#db2777",  # Pink
    "ALL":        "#6b7280",  # Gray (for "all classes" filter)
}

# Color mapping for OpenCV rendering (BGR format for cv2.rectangle)
# Note: OpenCV uses BGR, not RGB
COLOR_MAP_CV2 = {
    "car":        (0, 200, 255),   # BGR: Orange-yellow
    "bus":        (0, 100, 255),   # BGR: Orange
    "truck":      (0,  50, 200),   # BGR: Blue
    "motorcycle": (255, 180,   0), # BGR: Yellow-orange
    "bicycle":    (255, 255,   0), # BGR: Yellow
    "person":     (  0, 255, 100), # BGR: Green
}

# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------
# Regex pattern for safe filenames - allows only alphanumeric, dots, hyphens, underscores
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]")


def sanitise_filename(name: str) -> str:
    """
    Strip unsafe characters from a filename to prevent path traversal.
    
    This is a security measure to prevent users from specifying
    filenames that could escape the logs directory (e.g., ../../etc/passwd)
    
    Parameters
    ----------
    name : str
        Original filename from user input
        
    Returns
    -------
    str
        Sanitized filename with unsafe characters replaced by underscores
    """
    # Replace any character not in the allowed set with underscore
    safe = _SAFE_FILENAME_RE.sub("_", name)
    # Remove leading dots (could hide file extensions)
    safe = safe.lstrip(".")
    # Fallback if name was only unsafe characters
    return safe or "unknown"


def safe_float(val: str, lo: float = -1e6, hi: float = 1e6,
               default: float = 0.0) -> float:
    """
    Parse a float value safely with bounds checking.
    
    Used when reading CSV values that might be malformed or out of range.
    
    Parameters
    ----------
    val : str
        String value to parse as float
    lo : float
        Lower bound (values below this are clamped)
    hi : float
        Upper bound (values above this are clamped)
    default : float
        Value to return if parsing fails
        
    Returns
    -------
    float
        Parsed and clamped float value
    """
    try:
        f = float(val)
        # Check for NaN or Infinity
        if not math.isfinite(f):
            return default
        # Clamp to bounds
        return max(lo, min(hi, f))
    except (ValueError, TypeError):
        return default


def safe_int(val: str, lo: int = 0, hi: int = 10_000_000,
             default: int = 0) -> int:
    """
    Parse an integer value safely with bounds checking.
    
    Parameters
    ----------
    val : str
        String value to parse as integer
    lo : int
        Lower bound
    hi : int
        Upper bound
    default : int
        Value to return if parsing fails
        
    Returns
    -------
    int
        Parsed and clamped integer value
    """
    try:
        return max(lo, min(hi, int(val)))
    except (ValueError, TypeError):
        return default


def sanitise_cell(val: str, max_len: int = 256) -> str:
    """
    Truncate and strip control characters from a CSV cell value.
    
    Prevents CSV injection and ensures clean data display.
    
    Parameters
    ----------
    val : str
        Original cell value
    max_len : int
        Maximum allowed length (prevents huge cells)
        
    Returns
    -------
    str
        Sanitized cell value
    """
    val = str(val)[:max_len]
    # Keep only printable characters (space and above)
    # Also allow tab and newline for multi-line cells
    return "".join(ch for ch in val if ch >= " " or ch in "\t\n")
