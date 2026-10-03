from http.server import BaseHTTPRequestHandler

from lexicon.http_api import (
    api_key,
    handle_errors,
    json_response,
    ndjson_begin,
    ndjson_line,
    read_json,
    require_user,
    with_db,
)
from lexicon.notebook import talk
from lexicon.prefs import get_language, normalize_language
from lexicon.speak import speech_stream_payload


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        def run():
            user_id = require_user(self)
            body = read_json(self)
            key = api_key()

            def work(conn):
                language = normalize_language(
                    body.get("language") or get_language(conn, user_id)
                )
                reply = talk(
                    conn,
                    body.get("turns") or [],
                    key,
                    scene=body.get("scene") or "",
                    user_id=user_id,
                    language=language,
                )
                return language, reply

            language, reply = with_db(work)
            if not body.get("speak"):
                json_response(self, 200, reply)
                return

            # Stream the text reply first so the page can paint, then TTS.
            ndjson_begin(self)
            ndjson_line(self, reply)
            if reply.get("arabic"):
                ndjson_line(
                    self,
                    speech_stream_payload(reply["arabic"], key, language=language),
                )
            else:
                ndjson_line(self, {"audio_wav_base64": "", "error": "nothing to say"})

        handle_errors(self, run)

    def log_message(self, format, *args):
        return
