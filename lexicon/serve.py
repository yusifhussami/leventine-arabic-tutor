"""Local notebook for adding a lesson and practicing every saved word."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from lexicon.calendar_feed import calendar_connected, next_lesson, save_calendar_url
from lexicon.intake import item_kind, parse_lesson_text
from lexicon.judge import read_api_key
from lexicon.load import connect
from lexicon.notebook import judge_saved_item, list_items, save_lesson, search_items, similar_items

PAGE = Path(__file__).resolve().parent.parent / "web" / "index.html"
DB_PATH = Path("lexicon.db")


class NotebookHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._bytes(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/api/next-lesson":
            conn = connect(DB_PATH)
            try:
                if not calendar_connected(conn):
                    self._json(200, {"connected": False, "lesson": None})
                    return
                try:
                    lesson = next_lesson(conn)
                except Exception:
                    self._json(502, {"error": "could not read the calendar"})
                    return
                self._json(200, {"connected": True, "lesson": lesson})
            finally:
                conn.close()
            return
        if path == "/api/items":
            conn = connect(DB_PATH)
            try:
                query = parse_qs(urlparse(self.path).query).get("q", [""])[0]
                self._json(200, search_items(conn, query) if query.strip() else list_items(conn))
            finally:
                conn.close()
            return
        if path.startswith("/api/items/") and path.endswith("/similar"):
            item_id = path.removeprefix("/api/items/").removesuffix("/similar").strip("/")
            conn = connect(DB_PATH)
            try:
                self._json(200, similar_items(conn, int(item_id)))
            except ValueError:
                self._json(404, {"error": "not found"})
            finally:
                conn.close()
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "send JSON"})
            return
        try:
            if path == "/api/calendar":
                conn = connect(DB_PATH)
                try:
                    save_calendar_url(conn, body.get("url") or "")
                finally:
                    conn.close()
                self._json(200, {"connected": True})
                return
            if path == "/api/preview":
                pairs = parse_lesson_text(body.get("text") or "")
                self._json(
                    200,
                    [
                        {"spelling": spelling, "gloss": gloss, "kind": item_kind(spelling)}
                        for spelling, gloss in pairs
                    ],
                )
                return
            if path == "/api/lessons":
                conn = connect(DB_PATH)
                try:
                    saved = save_lesson(conn, body["learned_on"], body.get("text") or "")
                finally:
                    conn.close()
                self._json(200, saved)
                return
            if path == "/api/practice":
                conn = connect(DB_PATH)
                try:
                    result = judge_saved_item(
                        conn,
                        int(body["item_id"]),
                        body.get("sentence") or "",
                        read_api_key(),
                    )
                finally:
                    conn.close()
                self._json(200, result)
                return
        except (ValueError, KeyError, LookupError) as exc:
            self._json(400, {"error": str(exc)})
            return
        except RuntimeError as exc:
            self._json(502, {"error": str(exc)})
            return
        self._json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args) -> None:
        return

    def _json(self, status: int, payload) -> None:
        body = json.dumps(payload).encode()
        self._bytes(status, body, "application/json")

    def _bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main(argv: list[str] | None = None) -> None:
    global DB_PATH
    parser = argparse.ArgumentParser(description="Open the lesson notebook in a browser.")
    parser.add_argument("db_path", nargs="?", type=Path, default=Path("lexicon.db"))
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)
    DB_PATH = args.db_path
    connect(DB_PATH).close()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), NotebookHandler)
    print(f"http://127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
