from http.server import BaseHTTPRequestHandler

from lexicon.http_api import (
    api_key,
    handle_errors,
    json_response,
    query_param,
    read_json,
    require_user,
    with_db,
)
from lexicon.prefs import get_language, normalize_language
from lexicon.topics import generate_topics, list_topics, set_topic_status


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        def run():
            user_id = require_user(self)
            status = query_param(self, "status")

            def work(conn):
                language = normalize_language(
                    query_param(self, "language") or get_language(conn, user_id)
                )
                return {
                    "language": language,
                    "topics": list_topics(
                        conn,
                        user_id=user_id,
                        language=language,
                        status=status,
                    ),
                }

            json_response(self, 200, with_db(work))

        handle_errors(self, run)

    def do_POST(self):
        def run():
            user_id = require_user(self)
            body = read_json(self)

            def work(conn):
                language = normalize_language(
                    body.get("language") or get_language(conn, user_id)
                )
                return generate_topics(
                    conn,
                    api_key(),
                    user_id=user_id,
                    language=language,
                )

            json_response(self, 200, with_db(work))

        handle_errors(self, run)

    def do_PUT(self):
        def run():
            user_id = require_user(self)
            body = read_json(self)
            try:
                topic_id = int(query_param(self, "id"))
            except ValueError:
                raise ValueError("need a topic id")

            def work(conn):
                language = normalize_language(
                    body.get("language") or get_language(conn, user_id)
                )
                return set_topic_status(
                    conn,
                    topic_id,
                    body.get("status") or "",
                    user_id=user_id,
                    language=language,
                )

            json_response(self, 200, with_db(work))

        handle_errors(self, run)

    def log_message(self, format, *args):
        return
