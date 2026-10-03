from http.server import BaseHTTPRequestHandler

from lexicon.http_api import api_key, bytes_response, handle_errors, read_json, require_user
from lexicon.prefs import normalize_language
from lexicon.speak import speak_text


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        def run():
            require_user(self)
            body = read_json(self)
            audio = speak_text(
                body.get("text") or "",
                api_key(),
                language=normalize_language(body.get("language")),
            )
            bytes_response(self, 200, audio, "audio/wav")

        handle_errors(self, run)

    def log_message(self, format, *args):
        return
