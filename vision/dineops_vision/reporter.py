"""Talks to the DineOps SI server. Only table ids and counts ever leave this computer."""

from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from dineops_vision.counting import TableCount


class ReportError(Exception):
    """A problem to show the person running the camera, in plain words."""


@dataclass(frozen=True)
class TableInfo:
    id: int
    label: str
    seats: int


def check_server_url(url: str) -> str:
    """The camera key must not cross a network unencrypted."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ReportError("Enter the server address, like https://app.example.com")
    local = parts.hostname in ("localhost", "127.0.0.1", "::1")
    if parts.scheme == "http" and not local:
        raise ReportError("Use an https:// address for a server on another computer")
    return url.strip().rstrip("/")


class Reporter:
    def __init__(self, server_url: str, api_key: str, client: httpx.Client | None = None) -> None:
        self._root = f"{check_server_url(server_url)}/api/v1/ingest"
        self._headers = {"X-API-Key": api_key}
        self._client = client or httpx.Client(timeout=5)

    def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        try:
            response = self._client.request(
                method, f"{self._root}{path}", headers=self._headers, **kwargs  # type: ignore[arg-type]
            )
        except httpx.HTTPError as exc:
            raise ReportError("Can't reach the DineOps SI server") from exc
        if response.status_code == 401:
            raise ReportError("The server didn't accept the camera key")
        if response.status_code == 404:
            raise ReportError("A marked table no longer exists. Mark your tables again.")
        if response.status_code >= 400:
            raise ReportError(f"The server returned an error ({response.status_code})")
        return response

    def tables(self) -> list[TableInfo]:
        rows = self._request("GET", "/tables").json()
        return [TableInfo(row["id"], row["label"], row["seats"]) for row in rows]

    def send(self, counts: dict[int, TableCount]) -> int:
        """Returns how many tables changed on the server."""
        observations = [
            {"table_id": table, "guest_count": count.guests, "staff_present": count.staff}
            for table, count in counts.items()
        ]
        response = self._request("POST", "/observations", json={"observations": observations})
        return int(response.json()["changed"])
