import hashlib
import http.client
import json
import threading

import cv2
import httpx
import numpy as np
import pytest

from dineops_vision import engine as engine_module
from dineops_vision.camera import parse_source
from dineops_vision.counting import Box, Smoother, TableCount, Zone, count_tables, is_wearing
from dineops_vision.detector import ensure_model
from dineops_vision.engine import Engine, SetupError, load_settings
from dineops_vision.reporter import Reporter, ReportError, TableInfo, check_server_url
from dineops_vision.web import make_handler, make_server

FRAME = np.zeros((100, 200, 3), dtype=np.uint8)
LEFT = Zone(1, "T1", 0.0, 0.0, 0.5, 1.0)
RIGHT = Zone(2, "T2", 0.5, 0.0, 1.0, 1.0)


def person(x1=10.0, y1=10.0, x2=40.0, y2=90.0):
    return Box(x1, y1, x2, y2)


def painted(colour_bgr):
    frame = np.full((100, 100, 3), 200, dtype=np.uint8)
    frame[20:70, 20:80] = colour_bgr
    return frame


# Counting


def test_people_are_counted_at_their_own_table():
    people = [person(), person(20, 10, 50, 90), person(120, 10, 150, 90)]
    counts = count_tables(FRAME, people, [LEFT, RIGHT], None)
    assert counts == {1: TableCount(2, False), 2: TableCount(1, False)}


def test_person_walking_past_the_edge_does_not_count():
    assert count_tables(FRAME, [person(90, 10, 130, 90)], [LEFT], None)[1].guests == 0


def test_person_between_tables_counts_only_once():
    counts = count_tables(FRAME, [person(85, 10, 125, 90)], [LEFT, RIGHT], None)
    assert counts[1].guests + counts[2].guests == 1


def test_no_tables_marked_means_nothing_to_report():
    assert count_tables(FRAME, [person()], [], None) == {}


@pytest.mark.parametrize(
    ("bgr", "colour"),
    [
        ((0, 0, 220), "red"),
        ((0, 130, 240), "orange"),
        ((0, 220, 230), "yellow"),
        ((0, 200, 0), "green"),
        ((220, 60, 0), "blue"),
    ],
)
def test_apron_colours_are_recognised(bgr, colour):
    assert is_wearing(painted(bgr), Box(0, 0, 100, 100), colour)


@pytest.mark.parametrize("bgr", [(200, 200, 200), (20, 20, 20), (220, 60, 0)], ids=["pale", "dark", "other"])
def test_other_clothes_are_not_an_apron(bgr):
    assert not is_wearing(painted(bgr), Box(0, 0, 100, 100), "red")


def test_apron_wearer_is_staff_and_not_a_guest():
    frame = painted((0, 0, 220))
    counts = count_tables(frame, [Box(0, 0, 100, 100)], [Zone(1, "T1", 0, 0, 1, 1)], "red")
    assert counts[1] == TableCount(0, True)


def test_without_an_apron_setting_everyone_is_a_guest():
    frame = painted((0, 0, 220))
    counts = count_tables(frame, [Box(0, 0, 100, 100)], [Zone(1, "T1", 0, 0, 1, 1)], None)
    assert counts[1] == TableCount(1, False)


def test_box_outside_the_picture_is_safe():
    assert not is_wearing(FRAME, Box(500, 500, 600, 600), "red")


def test_one_bad_frame_does_not_change_the_count():
    smoother = Smoother()
    for _ in range(4):
        smoother.update({1: TableCount(2, False)})
    assert smoother.update({1: TableCount(0, True)})[1] == TableCount(2, False)


def test_a_real_change_comes_through_quickly():
    smoother = Smoother()
    for _ in range(5):
        smoother.update({1: TableCount(2, False)})
    results = [smoother.update({1: TableCount(0, False)})[1].guests for _ in range(3)]
    assert results[-1] == 0


# Server connection


def fake_server(status=200):
    calls = []

    def handler(request):
        calls.append(request)
        if status != 200:
            return httpx.Response(status, json={})
        if request.method == "GET":
            return httpx.Response(200, json=[{"id": 1, "label": "T1", "seats": 4}])
        return httpx.Response(200, json={"accepted": 1, "changed": 1})

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_only_counts_are_sent():
    client, calls = fake_server()
    reporter = Reporter("http://localhost:3000/", "dos_key", client)
    assert reporter.send({1: TableCount(3, True)}) == 1
    request = calls[0]
    assert str(request.url) == "http://localhost:3000/api/v1/ingest/observations"
    assert request.headers["x-api-key"] == "dos_key"
    assert json.loads(request.content) == {
        "observations": [{"table_id": 1, "guest_count": 3, "staff_present": True}]
    }


def test_tables_are_listed():
    client, _ = fake_server()
    assert Reporter("http://localhost:3000", "k", client).tables() == [TableInfo(1, "T1", 4)]


@pytest.mark.parametrize(
    ("status", "words"), [(401, "key"), (404, "no longer exists"), (500, "error")]
)
def test_server_errors_are_explained(status, words):
    client, _ = fake_server(status)
    with pytest.raises(ReportError, match=words):
        Reporter("http://localhost:3000", "k", client).tables()


def test_unreachable_server_is_explained():
    def handler(request):
        raise httpx.ConnectError("down")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(ReportError, match="Can't reach"):
        Reporter("http://localhost:3000", "k", client).send({1: TableCount()})


@pytest.mark.parametrize("url", ["http://app.example.com", "ftp://a.b", "nonsense"])
def test_key_never_crosses_a_network_unencrypted(url):
    with pytest.raises(ReportError):
        check_server_url(url)


@pytest.mark.parametrize("url", ["https://app.example.com", "http://localhost:3000", "http://127.0.0.1:3000"])
def test_safe_server_addresses_are_accepted(url):
    assert check_server_url(url) == url


# The main loop


class FakeDetector:
    def __init__(self, boxes=None):
        self.boxes = boxes or []

    def detect(self, frame):
        return self.boxes


class FakeCamera:
    def __init__(self, frame):
        self.frame = frame

    def latest(self):
        return self.frame

    def stop(self):
        pass


class FakeReporter:
    def __init__(self, error=None):
        self.sent = []
        self.error = error

    def tables(self):
        return [TableInfo(1, "T1", 4), TableInfo(2, "T2", 2)]

    def send(self, counts):
        if self.error:
            raise ReportError(self.error)
        self.sent.append(counts)
        return 0


@pytest.fixture
def running(tmp_path):
    engine = Engine(FakeDetector([person()]), tmp_path / "settings.json")
    engine._camera = FakeCamera(FRAME)
    engine._reporter = FakeReporter()
    engine.tables = engine._reporter.tables()
    engine.mark_table(LEFT)
    return engine


def test_sends_counts_only_after_being_started(running):
    running.tick()
    assert running._reporter.sent == []
    assert running.counts[1].guests == 1

    running.set_options(None, True)
    running.tick()
    assert running._reporter.sent[-1][1].guests == 1


def test_dead_camera_sends_nothing_so_tables_are_not_emptied(running):
    running.set_options(None, True)
    running.tick()
    before = len(running._reporter.sent)

    running._camera.frame = None
    running.tick()
    assert len(running._reporter.sent) == before
    assert running.camera_ok is False
    assert running.counts == {}


def test_server_problem_shows_then_clears(running):
    running.set_options(None, True)
    running._reporter.error = "Can't reach the DineOps SI server"
    running.tick()
    assert running.report_error == "Can't reach the DineOps SI server"
    running._reporter.error = None
    running.tick()
    assert running.report_error is None


def test_cannot_start_without_a_marked_table(running):
    running.unmark_table(1)
    with pytest.raises(SetupError, match="Mark at least one"):
        running.set_options(None, True)


@pytest.mark.parametrize(
    "zone",
    [Zone(99, "?", 0, 0, 1, 1), Zone(1, "T1", 0.5, 0, 0.2, 1), Zone(1, "T1", 0, 0, 1.5, 1)],
    ids=["other restaurant", "backwards", "outside picture"],
)
def test_bad_table_marks_are_refused(running, zone):
    with pytest.raises(SetupError):
        running.mark_table(zone)


def test_remarking_moves_a_table_and_keeps_the_others(running):
    running.mark_table(RIGHT)
    moved = Zone(1, "T1", 0.1, 0.1, 0.2, 0.2)
    running.mark_table(moved)
    assert sorted(running.settings.zones, key=lambda z: z.table_id) == [moved, RIGHT]


def test_removing_the_last_table_stops_sending(running):
    running.set_options(None, True)
    running.unmark_table(1)
    assert running.settings.reporting is False


def test_unknown_apron_colour_is_refused(running):
    with pytest.raises(SetupError):
        running.set_options("purple", None)


def test_settings_survive_a_restart(running, tmp_path):
    running.set_options("red", True)
    loaded = load_settings(tmp_path / "settings.json")
    assert loaded.zones == [LEFT]
    assert loaded.apron == "red"
    assert loaded.reporting is True


def test_changing_restaurant_clears_marks_and_stops_sending(running, monkeypatch):
    running.settings.api_key = "old-key"
    running.set_options(None, True)
    monkeypatch.setattr(engine_module, "Reporter", lambda url, key: FakeReporter())
    monkeypatch.setattr(engine_module, "Camera", FakeCamera)
    running.connect("http://localhost:3000", "new-key", "0")
    assert running.settings.zones == []
    assert running.settings.reporting is False


def test_connect_explains_missing_details(tmp_path):
    engine = Engine(FakeDetector(), tmp_path / "s.json")
    with pytest.raises(SetupError, match="camera key"):
        engine.connect("http://localhost:3000", "", "0")
    with pytest.raises(SetupError, match="camera address"):
        engine.connect("http://localhost:3000", "k", " ")


def test_camera_key_is_never_shown_back(running):
    running.settings.api_key = "dos_secret"
    assert "dos_secret" not in json.dumps(running.state())
    assert running.state()["has_key"] is True


def test_preview_marks_the_picture_and_handles_no_camera(running):
    running.tick()
    picture = running.preview_jpeg()
    assert cv2.imdecode(np.frombuffer(picture, np.uint8), cv2.IMREAD_COLOR).shape == FRAME.shape
    running._camera.frame = None
    running.tick()
    assert running.preview_jpeg() is None


def test_camera_source_numbers_mean_a_local_camera():
    assert parse_source("0") == 0
    assert parse_source(" http://1.2.3.4/video ") == "http://1.2.3.4/video"


# The setup page


@pytest.fixture
def page(running):
    server = make_server(running, 0)
    port = server.server_address[1]
    server.RequestHandlerClass = make_handler(running, port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield port, running
    server.shutdown()


def call(port, method, path, body=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    default = {"Content-Type": "application/json"} if body is not None else {}
    payload = json.dumps(body) if body is not None else None
    connection.request(method, path, payload, default | (headers or {}))
    response = connection.getresponse()
    return response.status, response.read()


def test_page_and_state_load(page):
    port, _ = page
    assert call(port, "GET", "/")[0] == 200
    status, body = call(port, "GET", "/api/state")
    assert status == 200
    assert json.loads(body)["zones"][0]["label"] == "T1"


def test_tables_can_be_marked_from_the_page(page):
    port, engine = page
    zone = {"table_id": 2, "x1": 0.1, "y1": 0.1, "x2": 0.4, "y2": 0.4}
    status, _ = call(port, "POST", "/api/zones/mark", zone)
    assert status == 200
    assert [z.label for z in engine.settings.zones] == ["T1", "T2"]
    assert call(port, "POST", "/api/zones/unmark", {"table_id": 1})[0] == 200
    assert [z.label for z in engine.settings.zones] == ["T2"]


def test_page_shows_setup_errors_in_plain_words(page):
    port, _ = page
    zone = {"table_id": 99, "x1": 0.1, "y1": 0.1, "x2": 0.4, "y2": 0.4}
    status, body = call(port, "POST", "/api/zones/mark", zone)
    assert status == 400
    assert "isn't in this restaurant" in json.loads(body)["detail"]


def test_other_websites_cannot_control_it(page):
    port, engine = page
    tricked = call(port, "POST", "/api/options", {"reporting": True}, {"Host": "evil.example.com"})
    assert tricked[0] == 403
    assert call(port, "GET", "/preview.mjpg", headers={"Host": "evil.example.com"})[0] == 403
    plain = call(port, "POST", "/api/options", {"reporting": True}, {"Content-Type": "text/plain"})
    assert plain[0] == 415
    assert engine.settings.reporting is False


def test_bad_requests_do_not_crash_it(page):
    port, _ = page
    assert call(port, "POST", "/api/zones/mark", {"wrong": 1})[0] == 400
    assert call(port, "POST", "/api/nothing", {})[0] == 400
    assert call(port, "GET", "/nothing")[0] == 404


# The model file


def test_model_must_match_its_checksum(tmp_path):
    source = tmp_path / "source.onnx"
    source.write_bytes(b"model")
    good = hashlib.sha256(b"model").hexdigest()
    target = tmp_path / "models" / "m.onnx"

    assert ensure_model(target, source.as_uri(), good) == target
    assert target.read_bytes() == b"model"

    with pytest.raises(RuntimeError, match="safety check"):
        ensure_model(tmp_path / "other.onnx", source.as_uri(), "0" * 64)
    assert not (tmp_path / "other.part").exists()


def test_tampered_model_is_replaced(tmp_path):
    source = tmp_path / "source.onnx"
    source.write_bytes(b"model")
    target = tmp_path / "m.onnx"
    target.write_bytes(b"tampered")
    ensure_model(target, source.as_uri(), hashlib.sha256(b"model").hexdigest())
    assert target.read_bytes() == b"model"
