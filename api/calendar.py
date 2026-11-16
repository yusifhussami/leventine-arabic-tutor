from http.server import BaseHTTPRequestHandler

from lexicon.http_api import (
    handle_errors,
    json_response,
    query_param,
    read_json,
    require_user,
    with_db,
)
from lexicon.calendar_feed import calendar_connected, next_lesson, save_calendar_url


class handler(BaseHTTPRequestHandler):
    """Calendar save, plus the next-lesson read.

    `/api/next-lesson` rewrites here (`?next=1`) so Topics can have its own
    function file without passing Vercel's 12-function cap.
    """

    def do_GET(self):
        def run():
            if query_param(self, "next") != "1":
                json_response(self, 404, {"error": "not found"})
                return
            user_id = require_user(self)

            def work(conn):
                if not calendar_connected(conn, user_id):
                    return {"connected": False, "lesson": None}
                try:
                    lesson = next_lesson(conn, user_id=user_id)
                except Exception:
                    raise RuntimeError("could not read the calendar")
                return {"connected": True, "lesson": lesson}

            json_response(self, 200, with_db(work))

        handle_errors(self, run)

    def do_POST(self):
        def run():
            user_id = require_user(self)
            body = read_json(self)

            def work(conn):
                save_calendar_url(conn, body.get("url") or "", user_id)
                return {"connected": True}

            json_response(self, 200, with_db(work))

        handle_errors(self, run)

    def log_message(self, format, *args):
        return
