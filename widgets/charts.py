"""
widgets/charts.py
~~~~~~~~~~~~~~~~~
Custom QPainter-based chart widgets for data visualization.

This module provides several chart widgets for the analysis panel:
- MiniBarChart: Vertical bar chart for class distributions
- MiniPieChart: Pie/donut chart for traffic mix proportions
- HeatmapWidget: 2D spatial heatmap of detection positions
- TrajectoryCanvas: Canvas for drawing object movement paths

All charts are implemented using QPainter for smooth rendering
without external charting dependencies.

Dependencies:
  - PyQt5.QtCore
  - PyQt5.QtGui
  - PyQt5.QtWidgets
  - constants.CLASS_PALETTE
"""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush,
    QLinearGradient, QPainterPath,
)
from PyQt5.QtWidgets import QWidget

from constants import CLASS_PALETTE


# ============================================================================
# MiniBarChart
# ============================================================================

class MiniBarChart(QWidget):
    """
    Vertical bar chart widget for displaying distributions.
    
    Used for:
    - Class distribution (number of detections per class)
    - Direction split (UP vs DOWN counts)
    - Average confidence by class
    
    Features:
    - Gradient-filled bars
    - Y-axis scale labels
    - X-axis category labels
    - Grid lines for readability
    """

    def __init__(self, parent=None):
        """
        Initialize the bar chart.
        
        Sets up empty data storage and minimum height.
        """
        super().__init__(parent)
        self._labels: list = []  # Category labels
        self._values: list = []  # Bar values
        self._colors: list = []  # Bar colors
        self.setMinimumHeight(170)

    def set_data(self, labels, values, colors=None):
        """
        Set the chart data.
        
        Parameters
        ----------
        labels : list
            List of category labels (e.g., class names)
        values : list
            List of numeric values for each category
        colors : list, optional
            List of hex color strings for each bar
        """
        self._labels = labels
        self._values = values
        self._colors = colors or ["#2563eb"] * len(labels)  # Default blue
        self.update()

    def paintEvent(self, _):
        """
        Render the bar chart using QPainter.
        
        Draws:
        - Grid lines
        - Y-axis scale
        - Gradient-filled bars with values on top
        - X-axis labels
        """
        if not self._values:
            return
        
        p  = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        
        # Margins: left=42, right=12, top=20, bottom=32
        PL, PR, PT, PB = 42, 12, 20, 32
        dw = W - PL - PR
        dh = H - PT - PB
        mx = max(self._values) or 1
        n  = len(self._values)
        gap = 8
        bw  = max(10, (dw - gap * (n + 1)) // n)

        # ── Grid lines ─────────────────────────────────────────────────
        p.setPen(QPen(QColor("#f3f4f6"), 1))
        for i in range(5):
            y = PT + dh * i // 4
            p.drawLine(PL, y, W - PR, y)

        # ── Y-axis scale ───────────────────────────────────────────────
        p.setPen(QColor("#9ca3af"))
        p.setFont(QFont("Segoe UI", 8))
        for i in range(5):
            v = mx * (4 - i) / 4
            y = PT + dh * i // 4
            p.drawText(0, y - 6, PL - 4, 14, Qt.AlignRight, str(int(v)))

        # ── Bars ───────────────────────────────────────────────────────
        for i, (lbl, val, col) in enumerate(
                zip(self._labels, self._values, self._colors)):
            x  = PL + gap + i * (bw + gap)
            bh = int(dh * val / mx)
            y  = PT + dh - bh

            # Gradient fill for bars
            grad = QLinearGradient(x, y, x, y + bh)
            grad.setColorAt(0, QColor(col))
            c2 = QColor(col); c2.setAlpha(140)
            grad.setColorAt(1, c2)
            p.setBrush(QBrush(grad))
            p.setPen(Qt.NoPen)
            path = QPainterPath()
            path.addRoundedRect(float(x), float(y), float(bw), float(bh), 4, 4)
            p.drawPath(path)

            # Value label on top of bar
            p.setPen(QColor("#374151"))
            p.setFont(QFont("Segoe UI", 8, QFont.Bold))
            p.drawText(x, max(4, y - 16), bw, 14, Qt.AlignCenter, str(val))

            # X-axis label below bar
            p.setPen(QColor("#6b7280"))
            p.setFont(QFont("Segoe UI", 7))
            p.drawText(x - 4, H - PB + 6, bw + 8, 20, Qt.AlignCenter, lbl[:7])

        p.end()


# ============================================================================
# MiniPieChart
# ============================================================================

class MiniPieChart(QWidget):
    """
    Pie / donut chart for displaying proportional data.
    
    Used for:
    - Traffic mix (percentage of each vehicle class)
    
    Features:
    - Donut-style pie (hollow center)
    - Color-coded segments
    - Legend with percentages on the right
    """

    def __init__(self, parent=None):
        """
        Initialize the pie chart.
        
        Sets up empty data storage and minimum size.
        """
        super().__init__(parent)
        self._labels: list = []
        self._values: list = []
        self._colors: list = []
        self.setMinimumSize(210, 180)

    def set_data(self, labels, values, colors=None):
        """
        Set the chart data.
        
        Parameters
        ----------
        labels : list
            List of category labels
        values : list
            List of numeric values
        colors : list, optional
            List of hex color strings
        """
        self._labels = labels
        self._values = values
        self._colors = colors or list(CLASS_PALETTE.values())
        self.update()

    def paintEvent(self, _):
        """
        Render the pie chart using QPainter.
        
        Draws:
        - Donut pie segments
        - Legend with color boxes and percentages
        """
        if not self._values:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H   = self.width(), self.height()
        total  = sum(self._values) or 1
        
        # Calculate donut dimensions
        r      = min(W // 2, H) // 2 - 14
        cx, cy = r + 14, H // 2

        # Draw pie segments
        angle = -90 * 16  # Start at top
        for i, (lbl, val) in enumerate(zip(self._labels, self._values)):
            span = int(360 * 16 * val / total)
            p.setBrush(QBrush(QColor(self._colors[i % len(self._colors)])))
            p.setPen(QPen(QColor("#ffffff"), 2))
            p.drawPie(cx - r, cy - r, 2 * r, 2 * r, angle, span)
            angle += span

        # Draw legend on the right
        lx = cx + r + 16
        ly = cy - len(self._labels) * 11
        p.setFont(QFont("Segoe UI", 8))
        for i, (lbl, val) in enumerate(zip(self._labels, self._values)):
            col = QColor(self._colors[i % len(self._colors)])
            p.setBrush(QBrush(col)); p.setPen(Qt.NoPen)
            p.drawRoundedRect(lx, ly + i * 20, 10, 10, 2, 2)
            p.setPen(QColor("#374151"))
            pct = f"{100 * val / total:.0f}%"
            p.drawText(lx + 14, ly + i * 20, 110, 14,
                       Qt.AlignLeft | Qt.AlignVCenter, f"{lbl}  {pct}")
        p.end()


# ============================================================================
# HeatmapWidget
# ============================================================================

class HeatmapWidget(QWidget):
    """
    2D spatial heatmap of detected object positions.
    
    Divides the frame into a 22x22 grid and counts detections
    in each cell to create a density heatmap.
    
    Used for:
    - Visualizing where objects are detected most frequently
    - Identifying high-traffic areas in the video
    
    Color gradient:
    - Low density: Blue (cool)
    - Medium density: Green/cyan
    - High density: Yellow/orange (hot)
    """

    # Grid size (22x22 cells)
    G = 22

    def __init__(self, parent=None):
        """
        Initialize the heatmap widget.
        
        Creates empty grid and sets minimum size.
        """
        super().__init__(parent)
        self._grid = [[0] * self.G for _ in range(self.G)]
        self._max  = 1
        self.setMinimumSize(260, 190)

    def set_points(self, points, w=640, h=480):
        """
        Calculate heatmap from detection center points.
        
        Parameters
        ----------
        points : list
            List of (cx, cy) center point tuples
        w : int
            Source frame width (default 640)
        h : int
            Source frame height (default 480)
        """
        G = self.G
        self._grid = [[0] * G for _ in range(G)]
        
        # Count points in each grid cell
        for cx, cy in points:
            gi = min(G - 1, max(0, int(cx * G / w)))
            gj = min(G - 1, max(0, int(cy * G / h)))
            self._grid[gj][gi] += 1
        
        # Find maximum for normalization
        self._max = max(max(row) for row in self._grid) or 1
        self.update()

    def paintEvent(self, _):
        """
        Render the heatmap using QPainter.
        
        Draws:
        - Dark background
        - Grid lines
        - Colored cells with alpha based on density
        """
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()
        G    = self.G
        cw, ch = W / G, H / G

        # Dark background
        p.fillRect(0, 0, W, H, QColor("#111827"))
        
        # Grid lines
        p.setPen(QPen(QColor(255, 255, 255, 10), 1))
        for i in range(G + 1):
            p.drawLine(int(i * cw), 0, int(i * cw), H)
            p.drawLine(0, int(i * ch), W, int(i * ch))

        # Colored cells based on density
        for j in range(G):
            for i in range(G):
                ratio = self._grid[j][i] / self._max
                if ratio < 0.001:
                    continue
                    
                # Color gradient based on density
                if ratio < 0.33:
                    # Blue to cyan
                    t = ratio / 0.33
                    r, g, b = 0, int(100 + t * 155), int(200 + t * 55)
                elif ratio < 0.66:
                    # Cyan to green
                    t = (ratio - 0.33) / 0.33
                    r, g, b = int(t * 255), 255, int(255 - t * 255)
                else:
                    # Green to yellow
                    t = (ratio - 0.66) / 0.34
                    r, g, b = 255, int(255 - t * 255), 0
                
                alpha = min(255, int(ratio * 240))
                p.fillRect(int(i * cw), int(j * ch),
                           int(cw) + 1, int(ch) + 1, QColor(r, g, b, alpha))
        p.end()


# ---------------------------------------------------------------------------
# TrajectoryCanvas
# ---------------------------------------------------------------------------
class TrajectoryCanvas(QWidget):
    """Movement trajectories of tracked objects, colour-coded by class."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tracks: dict = {}
        self.setMinimumSize(260, 190)

    def set_tracks(self, tracks: dict):
        self._tracks = tracks
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        W, H = self.width(), self.height()

        p.fillRect(0, 0, W, H, QColor("#111827"))
        p.setPen(QPen(QColor(255, 255, 255, 10), 1))
        for i in range(0, W, 30):
            p.drawLine(i, 0, i, H)
        for j in range(0, H, 30):
            p.drawLine(0, j, W, j)

        for tid, info in self._tracks.items():
            pts = info.get("points", [])
            if len(pts) < 2:
                continue
            col = QColor(CLASS_PALETTE.get(info.get("cls", "car"), "#6b7280"))
            for k in range(1, len(pts)):
                alpha = int(60 + 195 * k / len(pts))
                pen   = QPen(QColor(col.red(), col.green(), col.blue(), alpha), 1)
                p.setPen(pen)
                x0, y0 = pts[k - 1]
                x1, y1 = pts[k]
                p.drawLine(int(x0 * W / 640), int(y0 * H / 480),
                           int(x1 * W / 640), int(y1 * H / 480))

            lx, ly = pts[-1]
            p.setBrush(QBrush(col))
            p.setPen(QPen(QColor("#ffffff"), 1))
            p.drawEllipse(int(lx * W / 640) - 3, int(ly * H / 480) - 3, 6, 6)

        p.end()
