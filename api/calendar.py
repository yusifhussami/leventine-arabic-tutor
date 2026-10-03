from http.server import BaseHTTPRequestHandler

from lexicon.http_api import handle_errors, json_response, read_json, require_user, with_db
from lexicon.calendar_feed import save_calendar_url


class handler(BaseHTTPRequestHandler):
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
