"""Turns detected people into a guest count and a staff flag for each table."""

import statistics
from collections import deque
from dataclasses import dataclass

import cv2
import numpy as np

# How much of a person's box must be inside a table's area for them to count as at that table.
MIN_OVERLAP = 0.4
# How much of someone's torso must be the apron colour for them to count as staff.
MIN_APRON_SHARE = 0.25
SMOOTHING_FRAMES = 5

# Hue ranges on OpenCV's 0-179 scale. Red wraps around the end of the scale, so it has two.
APRON_HUES: dict[str, list[tuple[int, int]]] = {
    "red": [(0, 8), (172, 179)],
    "orange": [(9, 20)],
    "yellow": [(21, 34)],
    "green": [(35, 85)],
    "blue": [(95, 128)],
}


@dataclass(frozen=True)
class Box:
    """A detected person, in pixels."""

    x1: float
    y1: float
    x2: float
    y2: float
    score: float = 1.0


@dataclass(frozen=True)
class Zone:
    """A table's area on screen, as fractions of the image so it survives a resolution change."""

    table_id: int
    label: str
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass(frozen=True)
class TableCount:
    guests: int = 0
    staff: bool = False


def _overlap_share(box: Box, zone: Zone, width: int, height: int) -> float:
    left = max(box.x1, zone.x1 * width)
    top = max(box.y1, zone.y1 * height)
    right = min(box.x2, zone.x2 * width)
    bottom = min(box.y2, zone.y2 * height)
    if right <= left or bottom <= top:
        return 0.0
    area = (box.x2 - box.x1) * (box.y2 - box.y1)
    return (right - left) * (bottom - top) / area if area > 0 else 0.0


def is_wearing(frame: np.ndarray, box: Box, colour: str | None) -> bool:
    """Looks at the torso only, since the head, legs and background would dilute the colour."""
    hues = APRON_HUES.get(colour or "")
    if not hues:
        return False
    height = box.y2 - box.y1
    width = box.x2 - box.x1
    top, bottom = int(box.y1 + 0.2 * height), int(box.y1 + 0.65 * height)
    left, right = int(box.x1 + 0.2 * width), int(box.x2 - 0.2 * width)
    torso = frame[max(top, 0) : max(bottom, 0), max(left, 0) : max(right, 0)]
    if torso.size == 0:
        return False
    hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
    # Pale or dark pixels have an unreliable hue, so only vivid ones count.
    vivid = (hsv[..., 1] >= 90) & (hsv[..., 2] >= 60)
    matches = np.zeros(vivid.shape, dtype=bool)
    for low, high in hues:
        matches |= (hsv[..., 0] >= low) & (hsv[..., 0] <= high)
    return float(np.mean(vivid & matches)) >= MIN_APRON_SHARE


def count_tables(
    frame: np.ndarray, boxes: list[Box], zones: list[Zone], apron: str | None
) -> dict[int, TableCount]:
    """Each person counts once, at the table they overlap most."""
    height, width = frame.shape[:2]
    guests = {zone.table_id: 0 for zone in zones}
    staff = {zone.table_id: False for zone in zones}
    for box in boxes:
        best = max(
            zones, key=lambda zone: _overlap_share(box, zone, width, height), default=None
        )
        if best is None or _overlap_share(box, best, width, height) < MIN_OVERLAP:
            continue
        if is_wearing(frame, box, apron):
            staff[best.table_id] = True
        else:
            guests[best.table_id] += 1
    return {zone.table_id: TableCount(guests[zone.table_id], staff[zone.table_id]) for zone in zones}


class Smoother:
    """Evens out single-frame detection mistakes, so one bad frame doesn't change a count."""

    def __init__(self, frames: int = SMOOTHING_FRAMES) -> None:
        self._frames = frames
        self._history: dict[int, deque[TableCount]] = {}

    def reset(self) -> None:
        self._history.clear()

    def update(self, counts: dict[int, TableCount]) -> dict[int, TableCount]:
        self._history = {table: self._history.get(table, deque()) for table in counts}
        result = {}
        for table, count in counts.items():
            history = self._history[table]
            history.append(count)
            while len(history) > self._frames:
                history.popleft()
            result[table] = TableCount(
                guests=int(statistics.median_low(c.guests for c in history)),
                staff=sum(c.staff for c in history) * 2 > len(history),
            )
        return result
