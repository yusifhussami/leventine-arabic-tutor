from http.server import BaseHTTPRequestHandler

from lexicon.http_api import handle_errors, json_response, read_json, require_user
from lexicon.intake import item_kind, parse_lesson_text


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        def run():
            require_user(self)
            body = read_json(self)
            pairs = parse_lesson_text(body.get("text") or "")
            json_response(
                self,
                200,
                [
                    {"spelling": spelling, "gloss": gloss, "kind": item_kind(spelling)}
                    for spelling, gloss in pairs
                ],
            )

        handle_errors(self, run)

    def log_message(self, format, *args):
        return
