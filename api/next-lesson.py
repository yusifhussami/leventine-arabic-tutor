from http.server import BaseHTTPRequestHandler

from lexicon.http_api import handle_errors, json_response, require_user, with_db
from lexicon.calendar_feed import calendar_connected, next_lesson


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        def run():
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

    def log_message(self, format, *args):
        return
