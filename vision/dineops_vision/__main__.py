"""Start with: python -m dineops_vision"""

import argparse
import logging
import threading
import webbrowser
from pathlib import Path

from dineops_vision.detector import YoloxDetector, ensure_model
from dineops_vision.engine import Engine
from dineops_vision.web import HOST, make_server

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description="DineOps SI camera demo")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--settings", type=Path, default=ROOT / "settings.json")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    detector = YoloxDetector(ensure_model(ROOT / "models" / "yolox_tiny.onnx"))
    engine = Engine(detector, args.settings)
    engine.resume()
    threading.Thread(target=engine.run_forever, daemon=True).start()

    server = make_server(engine, args.port)
    url = f"http://{HOST}:{args.port}"
    logging.getLogger(__name__).info("Camera setup page: %s  (press Ctrl+C to stop)", url)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
