"""Read an Anki .apkg into plain decks and cards.

Word decks in Sawt never go through this module. An imported deck keeps the
front and back Anki stored, plus FSRS memory when the package has it, and
nothing is written into the lesson notebook.
"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone

from lexicon.fsrs import Memory, memory_from_sm2, normalize_retention, normalize_weights

_CLOZE = re.compile(r"\{\{c(\d+)::(.*?)(?:::(.*?))?\}\}", re.DOTALL)
_TAG = re.compile(r"(?is)<(script|style)\b.*?>.*?</\1>")
_BREAK = re.compile(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>")
_MARKUP = re.compile(r"(?s)<[^>]+>")
_SOUND = re.compile(r"\[sound:[^\]]+\]")
_COND = re.compile(r"\{\{#([^{}]+)\}\}(.*?)\{\{/\1\}\}", re.DOTALL)
_NEG = re.compile(r"\{\{\^([^{}]+)\}\}(.*?)\{\{/\1\}\}", re.DOTALL)
_FIELD = re.compile(r"\{\{([^{}]+)\}\}")
_MAX_ZIP_ENTRY = 40 * 1024 * 1024
_MAX_SQLITE = 80 * 1024 * 1024
_MAX_CARDS = 20000
_MAX_TEXT = 8000

ZSTD_HINT = (
    "This Anki deck uses the newer package format. Export it again with "
    "“Support older Anki versions”, or install zstandard "
    "(python3 -m pip install zstandard)."
)


def read_apkg(blob: bytes) -> list[dict]:
    """Return imported decks: name, weights, retention, and cards."""
    if not blob:
        raise ValueError("choose an Anki deck")
    try:
        archive = zipfile.ZipFile(__import__("io").BytesIO(blob))
    except zipfile.BadZipFile as exc:
        raise ValueError("that file isn’t an Anki deck") from exc
    names = set(archive.namelist())
    if "collection.anki21b" in names:
        raw = _read_entry(archive, "collection.anki21b")
        try:
            sqlite_bytes = decompress_zstd(raw)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(ZSTD_HINT) from exc
    elif "collection.anki21" in names:
        sqlite_bytes = _read_entry(archive, "collection.anki21")
    elif "collection.anki2" in names:
        sqlite_bytes = _read_entry(archive, "collection.anki2")
    else:
        raise ValueError("that file isn’t an Anki deck")
    if not sqlite_bytes.startswith(b"SQLite format 3"):
        raise ValueError("that file isn’t an Anki deck")
    if len(sqlite_bytes) > _MAX_SQLITE:
        raise ValueError("that deck is too large")
    return _decks_from_sqlite(sqlite_bytes)


def decompress_zstd(data: bytes) -> bytes:
    if data.startswith(b"SQLite format 3"):
        return data
    try:
        from compression import zstd

        return zstd.decompress(data)
    except Exception:
        pass
    try:
        import zstandard

        return zstandard.ZstdDecompressor().decompress(data, max_output_size=_MAX_SQLITE)
    except Exception:
        pass
    binary = shutil.which("zstd") or shutil.which("unzstd")
    if not binary:
        raise ValueError(ZSTD_HINT)
    result = subprocess.run(
        [binary, "-d", "-c"],
        input=data,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.startswith(b"SQLite format 3"):
        raise ValueError(ZSTD_HINT)
    return result.stdout


def _read_entry(archive: zipfile.ZipFile, name: str) -> bytes:
    info = archive.getinfo(name)
    if info.file_size > _MAX_ZIP_ENTRY:
        raise ValueError("that deck is too large")
    return archive.read(name)


def _decks_from_sqlite(blob: bytes) -> list[dict]:
    fd, path = tempfile.mkstemp(suffix=".anki2")
    os.close(fd)
    try:
        with open(path, "wb") as handle:
            handle.write(blob)
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            return _read_collection(conn)
        finally:
            conn.close()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    except sqlite3.Error:
        return set()


def _read_collection(conn: sqlite3.Connection) -> list[dict]:
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    if "notes" not in tables or "cards" not in tables:
        raise ValueError("that file isn’t an Anki deck")
    created = _collection_created(conn)
    if "decks" in tables and "name" in _columns(conn, "decks"):
        decks, weights = _schema18_decks(conn)
        models = _schema18_models(conn)
    else:
        decks, weights, models = _schema11_meta(conn)
    note_cols = _columns(conn, "notes")
    card_cols = _columns(conn, "cards")
    if "flds" not in note_cols or "did" not in card_cols:
        raise ValueError("that file isn’t an Anki deck")
    notes = {}
    for row in conn.execute("SELECT * FROM notes"):
        notes[row["id"]] = row
    grouped: dict[int, list[dict]] = {}
    total = 0
    for row in conn.execute("SELECT * FROM cards"):
        queue = row["queue"] if "queue" in card_cols else 0
        if queue == -1:
            continue
        note = notes.get(row["nid"])
        if note is None:
            continue
        rendered = _render_card(note, row, models)
        if rendered is None:
            continue
        front, back = rendered
        if not front and not back:
            continue
        card = _card_state(row, card_cols, created, front, back)
        grouped.setdefault(int(row["did"]), []).append(card)
        total += 1
        if total > _MAX_CARDS:
            raise ValueError("that deck has more cards than Sawt can take")
    imported = []
    used_names: dict[str, int] = {}
    for deck_id, cards in grouped.items():
        if not cards:
            continue
        meta = decks.get(deck_id, {})
        if meta.get("dynamic"):
            continue
        name = _unique_name(meta.get("name") or "Imported deck", used_names)
        preset = weights.get(meta.get("conf"))
        imported.append(
            {
                "name": name,
                "weights": preset["weights"] if preset else (),
                "retention": preset["retention"] if preset else 0.9,
                "cards": cards,
            }
        )
    if not imported:
        raise ValueError("that deck has no cards")
    return imported


def _collection_created(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute("SELECT crt FROM col LIMIT 1").fetchone()
    except sqlite3.Error:
        return 0
    if row is None:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 0


def _schema11_meta(conn: sqlite3.Connection) -> tuple[dict, dict, dict]:
    columns = _columns(conn, "col")
    select = "decks, models" + (", dconf" if "dconf" in columns else "")
    row = conn.execute(f"SELECT {select} FROM col LIMIT 1").fetchone()
    decks_json = json.loads(row["decks"] or "{}")
    models_json = json.loads(row["models"] or "{}")
    dconf_json = json.loads(row["dconf"] or "{}") if "dconf" in columns else {}
    decks = {}
    for key, deck in decks_json.items():
        decks[int(deck.get("id", key))] = {
            "name": deck.get("name") or "Imported deck",
            "dynamic": bool(deck.get("dyn")),
            "conf": deck.get("conf"),
        }
    presets = {}
    for key, preset in dconf_json.items():
        raw = preset.get("fsrsWeights") or preset.get("fsrsParams") or []
        weights = normalize_weights(raw)
        presets[preset.get("id", key)] = {
            "weights": weights or (),
            "retention": normalize_retention(preset.get("desiredRetention", 0.9)),
        }
    models = {}
    for key, model in models_json.items():
        models[int(model.get("id", key))] = model
    return decks, presets, models


def _schema18_decks(conn: sqlite3.Connection) -> tuple[dict, dict]:
    decks = {}
    for row in conn.execute("SELECT id, name FROM decks"):
        decks[int(row["id"])] = {"name": row["name"] or "Imported deck", "dynamic": False, "conf": None}
    return decks, {}


def _schema18_models(conn: sqlite3.Connection) -> dict:
    if "fields" not in {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }:
        return {}
    fields: dict[int, list[tuple[int, str]]] = {}
    for row in conn.execute("SELECT ntid, ord, name FROM fields ORDER BY ntid, ord"):
        fields.setdefault(int(row["ntid"]), []).append((int(row["ord"]), row["name"]))
    models = {}
    for ntid, pairs in fields.items():
        models[ntid] = {
            "flds": [{"name": name, "ord": ord_} for ord_, name in pairs],
            "tmpls": [],
            "type": 1 if _looks_like_cloze(pairs) else 0,
        }
    return models


def _looks_like_cloze(pairs: list[tuple[int, str]]) -> bool:
    return any(name.casefold() == "text" for _, name in pairs)


def _render_card(note, card, models: dict) -> tuple[str, str] | None:
    parts = (note["flds"] or "").split("\x1f")
    model = models.get(int(note["mid"])) if "mid" in note.keys() else None
    names = []
    if model:
        names = [field.get("name") or f"Field {index + 1}" for index, field in enumerate(model.get("flds") or [])]
    if len(names) < len(parts):
        names.extend(f"Field {index + 1}" for index in range(len(names), len(parts)))
    fields = {name: parts[index] if index < len(parts) else "" for index, name in enumerate(names)}
    ord_ = int(card["ord"] or 0)
    templates = (model or {}).get("tmpls") or []
    cloze_model = bool(model and (model.get("type") == 1 or _has_cloze(parts)))
    if templates and ord_ < len(templates) and not cloze_model:
        template = templates[ord_]
        front = _fill_template(template.get("qfmt") or "", fields, "front", ord_)
        back = _fill_template(template.get("afmt") or "", fields, "back", ord_, front_side=front)
        return _clip(front), _clip(back)
    if _has_cloze(parts):
        source = next((part for part in parts if _CLOZE.search(part)), parts[0])
        front = plain_text(render_cloze(source, ord_, "front"))
        back = plain_text(render_cloze(source, ord_, "back"))
        return _clip(front), _clip(back)
    if not parts:
        return None
    if ord_ == 0 or ord_ >= len(parts):
        front = parts[0]
        back = "\n".join(part for part in parts[1:] if part.strip())
    else:
        front = parts[ord_]
        back = parts[0]
    return _clip(plain_text(front)), _clip(plain_text(back))


def _has_cloze(parts: list[str]) -> bool:
    return any(_CLOZE.search(part or "") for part in parts)


def render_cloze(text: str, ord_index: int, side: str) -> str:
    number = ord_index + 1

    def replace(match: re.Match) -> str:
        which = int(match.group(1))
        answer = match.group(2)
        hint = match.group(3) or ""
        if which != number:
            return answer
        if side == "front":
            return f"[{hint}]" if hint else "[...]"
        return answer

    return _CLOZE.sub(replace, text)


def _fill_template(template: str, fields: dict, side: str, ord_index: int, front_side: str = "") -> str:
    text = template.replace("{{FrontSide}}", front_side)

    def keep_if(match: re.Match) -> str:
        name = match.group(1).strip()
        return match.group(2) if fields.get(name, "").strip() else ""

    def drop_if(match: re.Match) -> str:
        name = match.group(1).strip()
        return "" if fields.get(name, "").strip() else match.group(2)

    text = _COND.sub(keep_if, text)
    text = _NEG.sub(drop_if, text)

    def field(match: re.Match) -> str:
        token = match.group(1).strip()
        name = token.split(":")[-1].strip()
        value = fields.get(name, "")
        if token.lower().startswith("cloze:"):
            return render_cloze(value, ord_index, side)
        return value

    text = _FIELD.sub(field, text)
    return plain_text(text)


def plain_text(value: str) -> str:
    text = _TAG.sub("", value or "")
    text = _BREAK.sub("\n", text)
    text = _MARKUP.sub("", text)
    text = html.unescape(text)
    text = _SOUND.sub("", text)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _clip(value: str) -> str:
    value = value.strip()
    if len(value) <= _MAX_TEXT:
        return value
    return value[: _MAX_TEXT - 1].rstrip() + "…"


def _card_state(row, columns: set[str], created: int, front: str, back: str) -> dict:
    card_type = int(row["type"]) if "type" in columns else 0
    queue = int(row["queue"]) if "queue" in columns else card_type
    due = int(row["due"]) if "due" in columns else 0
    interval = int(row["ivl"]) if "ivl" in columns else 0
    factor = int(row["factor"]) if "factor" in columns else 0
    data = row["data"] if "data" in columns else ""
    now = datetime.now(timezone.utc)
    memory = _memory_from_data(data)
    if memory is None and card_type in (2, 3) and interval > 0:
        memory = memory_from_sm2(interval, factor / 1000.0 if factor else 2.5)
    if card_type == 0:
        state = "new"
        due_at = now
        stability = None
        difficulty = None
        scheduled_days = 0
        last_review = None
    elif card_type == 2:
        state = "review"
        due_at = _from_anki_day(created, due)
        stability = memory.stability if memory else None
        difficulty = memory.difficulty if memory else None
        scheduled_days = max(interval, 0)
        last_review = _from_anki_day(created, due - scheduled_days) if scheduled_days else None
    else:
        state = "relearning" if card_type == 3 else "learning"
        due_at = _learning_due(created, due, queue, now)
        stability = memory.stability if memory else None
        difficulty = memory.difficulty if memory else None
        scheduled_days = max(interval, 0)
        last_review = now
    remaining = 0
    if state in ("learning", "relearning") and "left" in columns:
        remaining = int(row["left"] or 0) % 1000
    return {
        "front": front,
        "back": back,
        "state": state,
        "stability": stability,
        "difficulty": difficulty,
        "due_at": due_at,
        "scheduled_days": scheduled_days,
        "learning_remaining": remaining,
        "reps": int(row["reps"]) if "reps" in columns else 0,
        "lapses": int(row["lapses"]) if "lapses" in columns else 0,
        "last_review_at": last_review,
        "suspended": False,
    }


def _memory_from_data(data: str):
    if not data or not str(data).lstrip().startswith("{"):
        return None
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return None
    stability = payload.get("s")
    difficulty = payload.get("d")
    if stability is None or difficulty is None:
        return None
    try:
        return Memory(float(stability), float(difficulty))
    except (TypeError, ValueError):
        return None


def _from_anki_day(created: int, days: int) -> datetime:
    return datetime.fromtimestamp(int(created) + int(days) * 86400, timezone.utc)


def _learning_due(created: int, due: int, queue: int, now: datetime) -> datetime:
    if queue == 3:
        return _from_anki_day(created, due)
    # Learning cards store a unix timestamp. Day numbers stay small.
    if due > 1_000_000_000:
        return datetime.fromtimestamp(due, timezone.utc)
    return now


def _unique_name(name: str, used: dict[str, int]) -> str:
    clean = " ".join((name or "").replace("::", " / ").split()) or "Imported deck"
    if len(clean) > 120:
        clean = clean[:119].rstrip() + "…"
    count = used.get(clean, 0) + 1
    used[clean] = count
    if count == 1:
        return clean
    return f"{clean} {count}"
