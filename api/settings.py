from http.server import BaseHTTPRequestHandler

from lexicon.http_api import handle_errors, json_response, read_json, require_user, with_db
from lexicon.prefs import get_language, save_language


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        def run():
            user_id = require_user(self)

            def work(conn):
                return {"language": get_language(conn, user_id)}

            json_response(self, 200, with_db(work))

        handle_errors(self, run)

    def do_POST(self):
        def run():
            user_id = require_user(self)
            body = read_json(self)

            def work(conn):
                return {"language": save_language(conn, body.get("language") or "", user_id)}

            json_response(self, 200, with_db(work))

        handle_errors(self, run)

    def log_message(self, format, *args):
        return
