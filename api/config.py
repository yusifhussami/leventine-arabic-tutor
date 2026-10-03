from http.server import BaseHTTPRequestHandler
import os

from lexicon.http_api import handle_errors, json_response


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        def run():
            json_response(
                self,
                200,
                {
                    "clerkPublishableKey": (os.environ.get("CLERK_PUBLISHABLE_KEY") or "").strip(),
                    "authRequired": True,
                },
            )

        handle_errors(self, run)

    def log_message(self, format, *args):
        return
