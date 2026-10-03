from http.server import BaseHTTPRequestHandler

from lexicon.http_api import api_key, handle_errors, json_response, read_json, require_user, with_db
from lexicon.notebook import talk


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        def run():
            user_id = require_user(self)
            body = read_json(self)

            def work(conn):
                return talk(
                    conn,
                    body.get("turns") or [],
                    api_key(),
                    scene=body.get("scene") or "",
                    user_id=user_id,
                )

            json_response(self, 200, with_db(work))

        handle_errors(self, run)

    def log_message(self, format, *args):
        return
