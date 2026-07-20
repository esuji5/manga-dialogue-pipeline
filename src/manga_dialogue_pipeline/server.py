"""Minimal read-only HTTP server for the search UI and API."""

from __future__ import annotations

import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .search import SearchIndex, SearchPolicy, SearchRequest


class SearchHandler(BaseHTTPRequestHandler):
    index: SearchIndex
    policy: SearchPolicy
    media_root: Path

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write(f"{self.address_string()} - {fmt % args}\n")

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        params = parse_qs(url.query)
        if url.path == "/":
            body = files("manga_dialogue_pipeline").joinpath("templates/search.html").read_bytes()
            return self._send(body, "text/html; charset=utf-8")
        if url.path == "/healthz":
            return self._json({"ok": True})
        if url.path == "/api/config":
            return self._json(self.index.config(self.policy))
        if url.path == "/api/search":
            return self._search(params)
        if url.path == "/media":
            return self._media(params)
        if url.path == "/favicon.ico":
            return self.send_error(404)
        self.send_error(404)

    def _search(self, params: dict[str, list[str]]) -> None:
        query = (params.get("q") or [""])[0]
        if len(query) > 300:
            return self._json({"error": "検索語は300文字以内にしてください"}, 400)
        try:
            limit = int((params.get("limit") or ["50"])[0])
        except ValueError:
            return self._json({"error": "limit must be an integer"}, 400)
        request = SearchRequest(
            query=query,
            works=tuple(params.get("work") or ()),
            speaker=(params.get("speaker") or [None])[0],
            exclude_unknown=(params.get("exclude_unknown") or ["0"])[0] == "1",
            page=(params.get("page") or [None])[0],
            panel=(params.get("panel") or [None])[0],
            limit=limit,
        )
        try:
            return self._json(self.index.search(request, self.policy))
        except Exception as exc:
            return self._json({"error": str(exc)}, 400)

    def _media(self, params: dict[str, list[str]]) -> None:
        work_id = (params.get("work") or [""])[0]
        page_id = (params.get("page") or [""])[0]
        if not work_id or not page_id:
            return self.send_error(400, "work and page required")
        path = self.index.media_path(work_id, page_id, self.policy, self.media_root)
        if not path:
            return self.send_error(404)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return self._send(path.read_bytes(), mime)

    def _json(self, value: object, status: int = 200) -> None:
        self._send(
            json.dumps(value, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
            status,
        )

    def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


def serve(
    *,
    database: Path,
    media_root: Path,
    host: str = "127.0.0.1",
    port: int = 8787,
    public: bool = False,
    full_content_works: frozenset[str] = frozenset(),
) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not public:
        raise ValueError("refusing a non-loopback bind without public=True")
    SearchHandler.index = SearchIndex(database)
    SearchHandler.policy = SearchPolicy(
        public=public,
        full_content_works=full_content_works,
    )
    SearchHandler.media_root = media_root.resolve()
    server = ThreadingHTTPServer((host, port), SearchHandler)
    mode = "public/redacted" if public else "local/full"
    print(f"Manga dialogue search: http://{host}:{port} ({mode})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        server.server_close()
