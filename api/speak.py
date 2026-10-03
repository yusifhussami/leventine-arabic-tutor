from http.server import BaseHTTPRequestHandler

from lexicon.http_api import api_key, bytes_response, handle_errors, read_json, require_user
from lexicon.speak import arabic_speech


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        def run():
            require_user(self)
            body = read_json(self)
            audio = arabic_speech(body.get("text") or "", api_key())
            bytes_response(self, 200, audio, "audio/wav")

        handle_errors(self, run)

    def log_message(self, format, *args):
        return
