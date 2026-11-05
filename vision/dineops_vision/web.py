"""The setup page, for this computer only. It shows the live picture and lets you mark tables."""

import json
import logging
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from dineops_vision.counting import Zone
from dineops_vision.engine import Engine, SetupError

logger = logging.getLogger(__name__)

HOST = "127.0.0.1"
PAGE = Path(__file__).with_name("setup.html")
PREVIEW_FRAME_SECONDS = 0.2
MAX_BODY_BYTES = 64 * 1024


def make_handler(engine: Engine, port: int) -> type[BaseHTTPRequestHandler]:
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - base class name.
            logger.debug(format, *args)

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, data: object) -> None:
            self._send(status, json.dumps(data).encode(), "application/json")

        def _host_allowed(self) -> bool:
            # Stops a website in the same browser from reaching this page by a trick address.
            if self.headers.get("Host") in allowed_hosts:
                return True
            self._json(403, {"detail": "Open this page at the address shown when it started"})
            return False

        def do_GET(self) -> None:  # noqa: N802 - base class name.
            if not self._host_allowed():
                return
            if self.path == "/":
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/api/state":
                self._json(200, engine.state())
            elif self.path == "/preview.mjpg":
                self._stream_preview()
            else:
                self._json(404, {"detail": "Not found"})

        def do_POST(self) -> None:  # noqa: N802 - base class name.
            if not self._host_allowed():
                return
            # Other websites can't send this content type here without the browser asking first,
            # and this server never says yes.
            if self.headers.get("Content-Type") != "application/json":
                self._json(415, {"detail": "Send JSON"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY_BYTES:
                self._json(413, {"detail": "Too much data"})
                return
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
                self._route_post(data)
                self._json(200, engine.state())
            except SetupError as exc:
                self._json(400, {"detail": str(exc)})
            except (ValueError, KeyError, TypeError):
                self._json(400, {"detail": "That request wasn't understood"})

        def _route_post(self, data: dict[str, Any]) -> None:
            if self.path == "/api/connect":
                engine.connect(str(data["server_url"]), str(data.get("api_key", "")), str(data["camera"]))
            elif self.path == "/api/zones/mark":
                table_id = int(data["table_id"])
                labels = {table.id: table.label for table in engine.tables}
                engine.mark_table(
                    Zone(
                        table_id=table_id,
                        label=labels.get(table_id, "?"),
                        x1=float(data["x1"]),
                        y1=float(data["y1"]),
                        x2=float(data["x2"]),
                        y2=float(data["y2"]),
                    )
                )
            elif self.path == "/api/zones/unmark":
                engine.unmark_table(int(data["table_id"]))
            elif self.path == "/api/options":
                engine.set_options(data.get("apron"), data.get("reporting"))
            else:
                raise KeyError(self.path)

        def _stream_preview(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                while True:
                    picture = engine.preview_jpeg()
                    if picture:
                        self.wfile.write(
                            b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                            + str(len(picture)).encode()
                            + b"\r\n\r\n"
                            + picture
                            + b"\r\n"
                        )
                    time.sleep(PREVIEW_FRAME_SECONDS)
            except OSError:
                return  # The page was closed.

    return Handler


def make_server(engine: Engine, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((HOST, port), make_handler(engine, port))
    server.daemon_threads = True
    return server
