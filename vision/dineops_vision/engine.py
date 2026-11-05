"""The main loop: read a frame, count people at each table, report the counts."""

import json
import logging
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import cv2
import numpy as np

from dineops_vision.camera import Camera
from dineops_vision.counting import (
    APRON_HUES,
    Box,
    Smoother,
    TableCount,
    Zone,
    count_tables,
    is_wearing,
)
from dineops_vision.detector import PersonDetector
from dineops_vision.reporter import Reporter, ReportError, TableInfo

logger = logging.getLogger(__name__)

TICK_SECONDS = 1.0


@dataclass
class Settings:
    server_url: str = "http://localhost:3000"
    api_key: str = ""
    camera: str = ""
    apron: str = ""
    reporting: bool = False
    zones: list[Zone] = field(default_factory=list)


def load_settings(path: Path) -> Settings:
    if not path.exists():
        return Settings()
    data = json.loads(path.read_text(encoding="utf-8"))
    data["zones"] = [Zone(**zone) for zone in data.get("zones", [])]
    return Settings(**data)


def save_settings(path: Path, settings: Settings) -> None:
    partial = path.with_suffix(".tmp")
    partial.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
    partial.replace(path)


class SetupError(Exception):
    """Something the person needs to correct on the setup page."""


class Engine:
    def __init__(self, detector: PersonDetector, settings_path: Path) -> None:
        self._detector = detector
        self._path = settings_path
        self._lock = threading.RLock()
        self.settings = load_settings(settings_path)
        self._camera: Camera | None = None
        self._reporter: Reporter | None = None
        self._smoother = Smoother()
        self._frame: np.ndarray | None = None
        self._boxes: list[Box] = []
        self.counts: dict[int, TableCount] = {}
        self.tables: list[TableInfo] = []
        self.camera_ok = False
        self.report_error: str | None = None
        self.last_sent_at: float | None = None
        self.seconds_per_check = 0.0

    def connect(self, server_url: str, api_key: str, camera: str) -> None:
        """Checks the server first, so a mistake shows up on the page instead of failing later."""
        key = api_key.strip() or self.settings.api_key
        if not key:
            raise SetupError("Enter the camera key from the app's Settings page")
        if not camera.strip():
            raise SetupError("Enter the camera address")
        try:
            reporter = Reporter(server_url, key)
            tables = reporter.tables()
        except ReportError as exc:
            raise SetupError(str(exc)) from exc

        with self._lock:
            restaurant_changed = key != self.settings.api_key
            self.settings.server_url = server_url.strip()
            self.settings.api_key = key
            if restaurant_changed:
                # Table ids belong to one restaurant, so old marks would report the wrong tables.
                self.settings.zones = []
                self.settings.reporting = False
            camera_changed = camera.strip() != self.settings.camera or self._camera is None
            self.settings.camera = camera.strip()
            self._reporter = reporter
            self.tables = tables
            if camera_changed:
                if self._camera:
                    self._camera.stop()
                self._camera = Camera(self.settings.camera)
                self.camera_ok = False
                self._smoother.reset()
            save_settings(self._path, self.settings)

    def resume(self) -> None:
        """Reconnects with saved settings when the program restarts."""
        if self.settings.api_key and self.settings.camera:
            try:
                self.connect(self.settings.server_url, "", self.settings.camera)
            except SetupError as exc:
                self.report_error = str(exc)

    def mark_table(self, zone: Zone) -> None:
        """Adds a table's area, or moves it if it's already marked."""
        if zone.table_id not in {table.id for table in self.tables}:
            raise SetupError("That table isn't in this restaurant")
        if not (0 <= zone.x1 < zone.x2 <= 1 and 0 <= zone.y1 < zone.y2 <= 1):
            raise SetupError("Draw the table's area inside the picture")
        with self._lock:
            others = [z for z in self.settings.zones if z.table_id != zone.table_id]
            self.settings.zones = [*others, zone]
            self._smoother.reset()
            save_settings(self._path, self.settings)

    def unmark_table(self, table_id: int) -> None:
        with self._lock:
            self.settings.zones = [z for z in self.settings.zones if z.table_id != table_id]
            if not self.settings.zones:
                self.settings.reporting = False
            self._smoother.reset()
            save_settings(self._path, self.settings)

    def set_options(self, apron: str | None, reporting: bool | None) -> None:
        with self._lock:
            if apron is not None:
                if apron and apron not in APRON_HUES:
                    raise SetupError("Choose one of the listed apron colours")
                self.settings.apron = apron
            if reporting is not None:
                if reporting and not self.settings.zones:
                    raise SetupError("Mark at least one table first")
                self.settings.reporting = reporting
                self.report_error = None
            save_settings(self._path, self.settings)

    def tick(self) -> None:
        camera = self._camera
        frame = camera.latest() if camera else None
        if frame is None:
            # Never report an empty room because the camera is down: that would mark tables
            # as vacated while guests are still sitting at them.
            with self._lock:
                self.camera_ok = False
                self._frame = None
                self._boxes = []
                self.counts = {}
                self._smoother.reset()
            return

        started = time.monotonic()
        boxes = self._detector.detect(frame)
        with self._lock:
            settings = self.settings
            zones = list(settings.zones)
            apron = settings.apron or None
            reporter = self._reporter if settings.reporting and zones else None
            smoothed = self._smoother.update(count_tables(frame, boxes, zones, apron))
            self.camera_ok = True
            self._frame = frame
            self._boxes = boxes
            self.counts = smoothed
            self.seconds_per_check = time.monotonic() - started

        if reporter is None:
            return
        try:
            reporter.send(smoothed)
        except ReportError as exc:
            with self._lock:
                self.report_error = str(exc)
            logger.warning("Couldn't report: %s", exc)
        else:
            with self._lock:
                self.report_error = None
                self.last_sent_at = time.monotonic()

    def run_forever(self) -> None:
        while True:
            started = time.monotonic()
            try:
                self.tick()
            except Exception:
                logger.exception("Camera check failed")
            time.sleep(max(0.0, TICK_SECONDS - (time.monotonic() - started)))

    def preview_jpeg(self) -> bytes | None:
        """The latest picture with people and tables marked. Stays on this computer."""
        with self._lock:
            camera = self._camera
            frame = camera.latest() if camera else None
            boxes = list(self._boxes)
            zones = list(self.settings.zones)
            counts = dict(self.counts)
            apron = self.settings.apron or None
        if frame is None:
            return None
        picture = frame.copy()
        height, width = picture.shape[:2]
        for box in boxes:
            colour = (0, 165, 255) if is_wearing(frame, box, apron) else (80, 200, 60)
            cv2.rectangle(picture, (int(box.x1), int(box.y1)), (int(box.x2), int(box.y2)), colour, 2)
        for zone in zones:
            count = counts.get(zone.table_id, TableCount())
            corner = (int(zone.x1 * width), int(zone.y1 * height))
            far = (int(zone.x2 * width), int(zone.y2 * height))
            cv2.rectangle(picture, corner, far, (255, 90, 60), 2)
            note = f"{zone.label}: {count.guests} guests" + (", staff" if count.staff else "")
            text_at = (corner[0] + 4, max(corner[1] - 6, 16))
            cv2.putText(picture, note, text_at, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
            cv2.putText(picture, note, text_at, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        ok, encoded = cv2.imencode(".jpg", picture, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return encoded.tobytes() if ok else None

    def state(self) -> dict[str, object]:
        """What the setup page shows. The camera key is never sent back, only whether one is saved."""
        with self._lock:
            sent_ago = time.monotonic() - self.last_sent_at if self.last_sent_at else None
            return {
                "server_url": self.settings.server_url,
                "has_key": bool(self.settings.api_key),
                "camera": self.settings.camera,
                "apron": self.settings.apron,
                "aprons": sorted(APRON_HUES),
                "reporting": self.settings.reporting,
                "connected": self._reporter is not None,
                "camera_ok": self.camera_ok,
                "report_error": self.report_error,
                "sent_seconds_ago": round(sent_ago, 1) if sent_ago is not None else None,
                "seconds_per_check": round(self.seconds_per_check, 2),
                "people_in_view": len(self._boxes),
                "tables": [asdict(table) for table in self.tables],
                "zones": [asdict(zone) for zone in self.settings.zones],
                "counts": {str(table): asdict(c) for table, c in self.counts.items()},
            }
