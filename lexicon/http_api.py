"""Shared helpers for Vercel Python API routes."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lexicon.db import open_db
from lexicon.judge import read_api_key


def json_response(handler, status: int, payload) -> None:
    body = json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def bytes_response(handler, status: int, body: bytes, content_type: str) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def ndjson_begin(handler, status: int = 200) -> None:
    """Start a streamed talk+speech response (reply line, then audio line)."""
    handler.send_response(status)
    handler.send_header("Content-Type", "application/x-ndjson")
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()


def ndjson_line(handler, payload) -> None:
    handler.wfile.write((json.dumps(payload) + "\n").encode())
    try:
        handler.wfile.flush()
    except Exception:
        pass


def read_json(handler) -> dict:
    length = int(handler.headers.get("Content-Length", "0") or "0")
    raw = handler.rfile.read(length) if length else b"{}"
    if not raw:
        return {}
    return json.loads(raw.decode())


def query_param(handler, name: str, default: str = "") -> str:
    return parse_qs(urlparse(handler.path).query).get(name, [default])[0]


def path_parts(handler) -> list[str]:
    return [part for part in urlparse(handler.path).path.split("/") if part]


def require_user(handler) -> str:
    """Return Clerk user id from the Bearer token."""
    auth = handler.headers.get("Authorization") or ""
    if not auth.startswith("Bearer "):
        raise PermissionError("sign in")
    token = auth[7:].strip()
    if not token:
        raise PermissionError("sign in")
    jwks = (os.environ.get("CLERK_JWKS_URL") or "").strip()
    if not jwks:
        raise RuntimeError("CLERK_JWKS_URL is not set")
    import jwt
    from jwt import PyJWKClient

    client = PyJWKClient(jwks)
    key = client.get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        key.key,
        algorithms=["RS256"],
        options={"verify_aud": False},
    )
    user_id = str(claims.get("sub") or "").strip()
    if not user_id:
        raise PermissionError("sign in")
    return user_id


def with_db(work):
    conn = open_db()
    try:
        return work(conn)
    finally:
        conn.close()


def api_key() -> str:
    return read_api_key()


def handle_errors(handler, run) -> None:
    try:
        run()
    except PermissionError as exc:
        json_response(handler, 401, {"error": str(exc)})
    except json.JSONDecodeError:
        json_response(handler, 400, {"error": "send JSON"})
    except (ValueError, KeyError, LookupError) as exc:
        json_response(handler, 400, {"error": str(exc)})
    except RuntimeError as exc:
        json_response(handler, 502, {"error": str(exc)})
