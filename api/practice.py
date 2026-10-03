from http.server import BaseHTTPRequestHandler

from lexicon.http_api import api_key, handle_errors, json_response, read_json, require_user, with_db
from lexicon.notebook import judge_saved_item
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
                return judge_saved_item(
                    conn,
                    int(body["item_id"]),
                    body.get("sentence") or "",
                    api_key(),
                    user_id=user_id,
                    language=language,
                )

            json_response(self, 200, with_db(work))

        handle_errors(self, run)

    def log_message(self, format, *args):
        return
