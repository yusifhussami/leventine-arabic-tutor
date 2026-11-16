from http.server import BaseHTTPRequestHandler

from lexicon.http_api import (
    handle_errors,
    json_response,
    query_param,
    read_json,
    require_user,
    with_db,
)
from lexicon.intake import item_kind, parse_lesson_text
from lexicon.notebook import save_lesson
from lexicon.prefs import get_language


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        def run():
            user_id = require_user(self)
            body = read_json(self)
            if query_param(self, "preview") == "1" or body.get("preview"):

                def preview(conn):
                    # Same language save_lesson uses, so the preview rows match
                    # the words that land in the list.
                    language = get_language(conn, user_id)
                    pairs = parse_lesson_text(body.get("text") or "", language=language)
                    return [
                        {
                            "spelling": spelling,
                            "gloss": gloss,
                            "kind": item_kind(spelling),
                        }
                        for spelling, gloss in pairs
                    ]

                json_response(self, 200, with_db(preview))
                return

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
