"""Reads a camera on its own thread and keeps only the newest frame, so video never lags behind."""

import logging
import threading
import time

import cv2
import numpy as np

logger = logging.getLogger(__name__)

RECONNECT_SECONDS = 3.0
# After this long with no new picture, the camera counts as down.
MAX_FRAME_AGE_SECONDS = 5.0


def parse_source(source: str) -> str | int:
    """A plain number means a camera attached to this computer."""
    return int(source) if source.strip().isdigit() else source.strip()


class Camera:
    def __init__(self, source: str) -> None:
        self._source = parse_source(source)
        self._lock = threading.Lock()
        self._frame: np.ndarray | None = None
        self._frame_time = 0.0
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def latest(self) -> np.ndarray | None:
        """The newest frame, or None if the camera isn't currently working."""
        with self._lock:
            if self._frame is None or time.monotonic() - self._frame_time > MAX_FRAME_AGE_SECONDS:
                return None
            return self._frame

    def stop(self) -> None:
        self._stopped.set()

    def _run(self) -> None:
        while not self._stopped.is_set():
            capture = cv2.VideoCapture(self._source)
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if capture.isOpened():
                self._read_until_failure(capture)
            capture.release()
            self._stopped.wait(RECONNECT_SECONDS)

    def _read_until_failure(self, capture: cv2.VideoCapture) -> None:
        frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        # A saved video plays back at its own speed and loops. A live camera reports no length.
        is_file = frame_count > 0
        delay = 1 / (capture.get(cv2.CAP_PROP_FPS) or 25) if is_file else 0.0
        while not self._stopped.is_set():
            ok, frame = capture.read()
            if not ok:
                if is_file:
                    capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                logger.warning("Lost the camera. Trying again...")
                return
            with self._lock:
                self._frame = frame
                self._frame_time = time.monotonic()
            if delay:
                time.sleep(delay)
