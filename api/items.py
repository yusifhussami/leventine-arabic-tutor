from http.server import BaseHTTPRequestHandler

from lexicon.arabic_script import fill_arabic_items
from lexicon.arwords import match_notebook
from lexicon import wordbook
from lexicon.http_api import (
    file_response,
    handle_errors,
    json_response,
    query_param,
    read_json,
    require_user,
    with_db,
)
from lexicon.notebook import export_words_csv, list_items, search_items
from lexicon.prefs import get_language


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        def run():
            user_id = require_user(self)
            action = query_param(self, "action")
            if action in {"dictionary", "dictionary-entry", "family"}:
                json_response(self, 200, with_db(lambda conn: wordbook.dispatch_get(conn, user_id, action, query_param(self, "q"), query_param(self, "id"))))
                return
            query = query_param(self, "q")
            # Same function as the word list. Hobby allows 12 files under api/.
            export_format = query_param(self, "format").strip().lower()

            def work(conn):
                language = get_language(conn, user_id)
                if export_format == "csv":
                    filename, text = export_words_csv(
                        conn, user_id=user_id, language=language
                    )
                    return ("csv", filename, text)
                if query.strip():
                    return (
                        "json",
                        search_items(conn, query, user_id=user_id, language=language),
                    )
                return ("json", list_items(conn, user_id=user_id, language=language))

            kind, *rest = with_db(work)
            if kind == "csv":
                filename, text = rest
                file_response(
                    self,
                    text.encode("utf-8"),
                    "text/csv; charset=utf-8",
                    filename,
                )
                return
            json_response(self, 200, rest[0])

        handle_errors(self, run)

    def do_POST(self):
        def run():
            user_id = require_user(self)
            body = read_json(self)
            action = (body.get("action") or "").strip()
            if action in {"save-dictionary", "save-family", "dictionary-forms", "suggest-family"}:
                json_response(self, 200, with_db(lambda conn: wordbook.dispatch_post(conn, user_id, body)))
                return
            if action not in {"fill-arabic", "match-arwords"}:
                json_response(self, 404, {"error": "not found"})
                return

            def work(conn):
                if action == "match-arwords":
                    return match_notebook(conn, user_id)
                # Best-effort after a save. The lesson itself is already stored.
                return fill_arabic_items(
                    conn,
                    user_id=user_id,
                    item_ids=body.get("ids"),
                    limit=16,
                )

            json_response(self, 200, with_db(work))

        handle_errors(self, run)

    def log_message(self, format, *args):
        return
