from http.server import BaseHTTPRequestHandler

from lexicon.http_api import handle_errors, json_response, query_param, require_user, with_db
from lexicon.notebook import similar_items


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        def run():
            user_id = require_user(self)
            item_id = int(query_param(self, "id"))

            def work(conn):
                return similar_items(conn, item_id, user_id=user_id)

            json_response(self, 200, with_db(work))

        handle_errors(self, run)

    def log_message(self, format, *args):
        return
