from http.server import BaseHTTPRequestHandler

from lexicon.http_api import handle_errors, json_response, read_json, require_user, with_db
from lexicon.notebook import save_lesson
from lexicon.prefs import get_language


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        def run():
            user_id = require_user(self)
            body = read_json(self)

            def work(conn):
                return save_lesson(
                    conn,
                    body["learned_on"],
                    body.get("text") or "",
                    user_id=user_id,
                    language=get_language(conn, user_id),
                )

            json_response(self, 200, with_db(work))

        handle_errors(self, run)

    def log_message(self, format, *args):
        return
