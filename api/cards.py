from http.server import BaseHTTPRequestHandler

from lexicon.cards import dispatch_get, dispatch_post, import_apkg
from lexicon.http_api import handle_errors, json_response, query_param, read_json, require_user, with_db


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        def run():
            user_id = require_user(self)

            def work(conn):
                return dispatch_get(
                    conn,
                    user_id,
                    query_param(self, "id"),
                    query_param(self, "action"),
                )

            json_response(self, 200, with_db(work))

        handle_errors(self, run)

    def do_POST(self):
        def run():
            user_id = require_user(self)
            action = query_param(self, "action")
            if action == "import":
                length = int(self.headers.get("Content-Length", "0") or "0")
                if length <= 0:
                    raise ValueError("choose an Anki deck")
                if length > 32 * 1024 * 1024:
                    raise ValueError("that deck is too large")
                raw = self.rfile.read(length)

                def work(conn):
                    return import_apkg(conn, raw, user_id=user_id)

                json_response(self, 200, with_db(work))
                return
            body = read_json(self)

            def work(conn):
                return dispatch_post(
                    conn,
                    user_id,
                    query_param(self, "id"),
                    action,
                    body,
                )

            json_response(self, 200, with_db(work))

        handle_errors(self, run)

    def log_message(self, format, *args):
        return
