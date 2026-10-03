from http.server import BaseHTTPRequestHandler

from lexicon.http_api import handle_errors, json_response, query_param, require_user, with_db
from lexicon.notebook import drop_exact_duplicates, list_items, search_items
from lexicon.prefs import get_language


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        def run():
            user_id = require_user(self)
            query = query_param(self, "q")

            def work(conn):
                language = get_language(conn, user_id)
                drop_exact_duplicates(conn, user_id, language=language)
                if query.strip():
                    return search_items(conn, query, user_id=user_id, language=language)
                return list_items(conn, user_id=user_id, language=language)

            json_response(self, 200, with_db(work))

        handle_errors(self, run)

    def log_message(self, format, *args):
        return
