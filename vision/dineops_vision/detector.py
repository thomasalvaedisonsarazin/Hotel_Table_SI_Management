"""Finds people in a frame with YOLOX-Tiny, an Apache-2.0 model that runs on an ordinary laptop."""

import hashlib
import logging
import urllib.request
from pathlib import Path
from typing import Protocol

import cv2
import numpy as np
import onnxruntime as ort

from dineops_vision.counting import Box

logger = logging.getLogger(__name__)

MODEL_URL = "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_tiny.onnx"
MODEL_SHA256 = "427cc366d34e27ff7a03e2899b5e3671425c262ea2291f88bb942bc1cc70b0f7"

_INPUT_SIZE = 416
_STRIDES = (8, 16, 32)
_PERSON_CLASS = 0
_MIN_SCORE = 0.35
_NMS_OVERLAP = 0.45


class PersonDetector(Protocol):
    def detect(self, frame: np.ndarray) -> list[Box]: ...


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_model(path: Path, url: str = MODEL_URL, expected: str = MODEL_SHA256) -> Path:
    """Downloads the model on first run, and refuses a file that isn't exactly the one we tested."""
    if path.exists() and _sha256(path) == expected:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    logger.info("Downloading the detection model (about 20 MB)...")
    urllib.request.urlretrieve(url, partial)  # noqa: S310 - fixed https address, checked below.
    if _sha256(partial) != expected:
        partial.unlink()
        raise RuntimeError("The downloaded model failed its safety check, so it wasn't used.")
    partial.replace(path)
    return path


def _grids(size: int) -> tuple[np.ndarray, np.ndarray]:
    grids, strides = [], []
    for stride in _STRIDES:
        cells = size // stride
        xs, ys = np.meshgrid(np.arange(cells), np.arange(cells))
        grids.append(np.stack((xs, ys), 2).reshape(-1, 2))
        strides.append(np.full((cells * cells, 1), stride))
    return np.concatenate(grids), np.concatenate(strides)


class YoloxDetector:
    def __init__(self, model_path: Path, threads: int = 2) -> None:
        options = ort.SessionOptions()
        # Keeps it from taking over a small laptop.
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(model_path), options, providers=["CPUExecutionProvider"]
        )
        self._input = self._session.get_inputs()[0].name
        self._grid, self._stride = _grids(_INPUT_SIZE)

    def detect(self, frame: np.ndarray) -> list[Box]:
        height, width = frame.shape[:2]
        ratio = min(_INPUT_SIZE / height, _INPUT_SIZE / width)
        resized = cv2.resize(frame, (int(width * ratio), int(height * ratio)))
        canvas = np.full((_INPUT_SIZE, _INPUT_SIZE, 3), 114, dtype=np.uint8)
        canvas[: resized.shape[0], : resized.shape[1]] = resized
        tensor = canvas.transpose(2, 0, 1)[None].astype(np.float32)

        raw = self._session.run(None, {self._input: tensor})[0][0]
        scores = raw[:, 4] * raw[:, 5 + _PERSON_CLASS]
        keep = scores >= _MIN_SCORE
        if not keep.any():
            return []
        centres = (raw[keep, :2] + self._grid[keep]) * self._stride[keep]
        sizes = np.exp(raw[keep, 2:4]) * self._stride[keep]
        corners = np.concatenate((centres - sizes / 2, sizes), axis=1) / ratio
        kept_scores = scores[keep]

        chosen = cv2.dnn.NMSBoxes(
            corners.tolist(), kept_scores.tolist(), _MIN_SCORE, _NMS_OVERLAP
        )
        boxes = []
        for index in np.array(chosen).reshape(-1):
            x, y, w, h = corners[index]
            boxes.append(
                Box(
                    x1=max(float(x), 0.0),
                    y1=max(float(y), 0.0),
                    x2=min(float(x + w), float(width)),
                    y2=min(float(y + h), float(height)),
                    score=float(kept_scores[index]),
                )
            )
        return boxes
