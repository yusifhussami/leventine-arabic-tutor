from http.server import BaseHTTPRequestHandler

from lexicon.http_api import handle_errors, json_response, read_json, require_user, with_db
from lexicon.notebook import import_csv
from lexicon.prefs import get_language, normalize_language


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        def run():
            user_id = require_user(self)
            body = read_json(self)

            def work(conn):
                language = normalize_language(
                    body.get("language") or get_language(conn, user_id)
                )
                return import_csv(
                    conn,
                    body.get("csv") or "",
                    user_id=user_id,
                    default_day=body.get("learned_on") or None,
                    language=language,
                )

            json_response(self, 200, with_db(work))

        handle_errors(self, run)

    def log_message(self, format, *args):
        return
