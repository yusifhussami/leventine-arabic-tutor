"""Levantine Arabic script for a saved Arabizi spelling.

Living Arabic's terms forbid automated access, and Levantine Dictionary does
not publish an API. The check against a dictionary goes through the English
Wiktionary Action API, which MediaWiki documents for this kind of read: one
request at a time, a named User-Agent, maxlag, and a local cache. Pages are
not scraped.

Arabizi has no single spelling, so the English gloss picks the Wiktionary
sense and the Arabizi picks which translation line (North or South Levantine
first). A miss falls through to the same OpenRouter model the rest of Sawt
uses. A spelling the learner typed is stored as user and is never replaced.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from lexicon.db import open_db
from lexicon.judge import MODEL, RateLimiter, _json_body, complete, message_text, read_api_key
from lexicon.load import normalize_meaning, normalize_word

SOURCE_DICTIONARY = "dictionary"
SOURCE_AI = "ai"
SOURCE_USER = "user"
SOURCES = frozenset({SOURCE_DICTIONARY, SOURCE_AI, SOURCE_USER})

WIKTIONARY_API = "https://en.wiktionary.org/w/api.php"
USER_AGENT = (
    "Sawt/1.0 (https://github.com/yusifhussami/leventine-arabic-tutor; "
    "Levantine Arabic tutor) Python-urllib"
)
_DICT_PACE = RateLimiter(min_interval=1.0)
_LLM_PACE = RateLimiter(min_interval=0.4)
_PAGE_TTL = timedelta(days=14)
_TITLE_BATCH = 20
_LEVANT_MIN = 0.74
_OTHER_MIN = 0.9

_STOP = frozenset(
    "a an the to of and or for my your his her their our i you he she we they it is was be am are".split()
)
_DIACRITICS = set("ًٌٍَُِّْـٰٱ")
_PUNCT = set("؟?!！.،,;؛:\"'“”()[]")
_ARABIC_RUN = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]+")
_EDGE_PUNCT = "؟?!！.،,;؛:ـ\"'“”"
_TEMPLATE = re.compile(r"\{\{(?:t|tt)\+?\|([^{}]+)\}\}", re.IGNORECASE)

_PAIRS = {
    "3'": "ɣ",
    "9'": "ḍ",
    "gh": "ɣ",
    "kh": "x",
    "sh": "š",
    "ch": "š",
    "th": "θ",
    "dh": "ð",
}
_ONE = {
    "2": "ʔ",
    "3": "ʕ",
    "5": "x",
    "6": "ṭ",
    "7": "ḥ",
    "8": "q",
    "9": "ṣ",
    "b": "b",
    "d": "d",
    "f": "f",
    "g": "g",
    "h": "h",
    "j": "j",
    "k": "k",
    "l": "l",
    "m": "m",
    "n": "n",
    "q": "q",
    "r": "r",
    "s": "s",
    "t": "t",
    "w": "w",
    "y": "y",
    "z": "z",
    "p": "p",
    "'": "ʔ",
}
_SUN = {
    "ب": "b",
    "ت": "t",
    "ث": "θ",
    "ج": "j",
    "ح": "ḥ",
    "خ": "x",
    "د": "d",
    "ذ": "ð",
    "ر": "r",
    "ز": "z",
    "س": "s",
    "ش": "š",
    "ص": "ṣ",
    "ض": "ḍ",
    "ط": "ṭ",
    "ظ": "ẓ",
    "ع": "ʕ",
    "غ": "ɣ",
    "ف": "f",
    "ق": "q",
    "ك": "k",
    "ل": "l",
    "م": "m",
    "ن": "n",
    "ه": "h",
    "پ": "p",
    "چ": "č",
    "گ": "g",
    "ڤ": "v",
}
_VOWEL_LETTERS = set("اأإآى")
_HAMZA = set("ءؤئ")

_AI_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "arabic": {"type": "string"},
                },
                "required": ["id", "arabic"],
            },
        }
    },
    "required": ["items"],
}


def clean_arabic(text: str) -> str:
    """Keep Arabic letters (and their diacritics) and drop a trailing question mark."""
    parts = []
    for part in _ARABIC_RUN.findall(text or ""):
        piece = part.strip(_EDGE_PUNCT).strip()
        if piece:
            parts.append(piece)
    return " ".join(parts).strip()


def gloss_heads(gloss: str) -> list[str]:
    """Up to two Wiktionary titles for an English gloss.

    The full phrase comes first (`how are you`), then a content word
    (`search` from `to search`). A slash offers another sense.
    """
    text = re.sub(r"\([^)]*\)", " ", gloss or "")
    heads: list[str] = []
    for chunk in re.split(r"[/|;]", text):
        words = re.findall(r"[A-Za-z']+", chunk)
        kept = [word for word in words if word.casefold() not in {"a", "an", "the", "to"}]
        if not kept:
            continue
        phrase = " ".join(word.casefold() for word in kept)
        if phrase not in heads:
            heads.append(phrase)
        content = [word.casefold() for word in kept if word.casefold() not in _STOP]
        if content and content[-1] not in heads:
            heads.append(content[-1])
        if len(heads) >= 2:
            break
    return heads[:2]


def arabizi_skeleton(text: str) -> str:
    """Consonants only, using this notebook's digit map."""
    raw = (
        (text or "")
        .strip()
        .casefold()
        .replace("’", "'")
        .replace("‘", "'")
        .replace("`", "'")
        .replace("-", "")
        .replace(" ", "")
    )
    out: list[str] = []
    index = 0
    while index < len(raw):
        pair = raw[index : index + 2]
        if pair in _PAIRS:
            out.append(_PAIRS[pair])
            index += 2
            continue
        token = _ONE.get(raw[index])
        if token:
            out.append(token)
        index += 1
    return "".join(out)


def _arabic_letters(text: str) -> list[tuple[str, str]]:
    letters: list[tuple[str, str]] = []
    for char in text or "":
        if char in _DIACRITICS or char in _PUNCT or char.isspace():
            continue
        if char in _SUN:
            letters.append(("C", _SUN[char]))
        elif char in _VOWEL_LETTERS:
            letters.append(("V", ""))
        elif char in _HAMZA:
            letters.append(("C", "ʔ"))
        elif char == "ة":
            letters.append(("T", "h"))
        elif char == "و":
            letters.append(("W", "w"))
        elif char == "ي":
            letters.append(("W", "y"))
    return letters


def arabic_skeletons(text: str) -> list[str]:
    """A few consonant readings. ي and و are sometimes long vowels."""
    letters = _arabic_letters(text)
    roles: list[tuple[str, str]] = []
    for index, (role, token) in enumerate(letters):
        if role != "W":
            roles.append((role, token))
            continue
        prev = letters[index - 1][0] if index else "C"
        nxt = letters[index + 1][0] if index + 1 < len(letters) else "C"
        if prev in {"C", "W", "T"} and nxt in {"C", "T"}:
            roles.append(("V", ""))
        else:
            roles.append((role, token))

    def spell(items: list[tuple[str, str]], ta_as_h: bool) -> str:
        out: list[str] = []
        for role, token in items:
            if role in {"C", "W"}:
                out.append(token)
            elif role == "T" and ta_as_h:
                out.append("h")
        return "".join(out)

    found = [spell(letters, False), spell(letters, True), spell(roles, False), spell(roles, True)]
    unique: list[str] = []
    for item in found:
        if item and item not in unique:
            unique.append(item)
    return unique


def _levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, start=1):
        current = [i]
        for j, b in enumerate(right, start=1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1]


def _ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return 1 - _levenshtein(left, right) / max(len(left), len(right))


def _loose(text: str) -> str:
    folded = (text or "").casefold()
    for src, dst in (
        ("ā", "a"),
        ("á", "a"),
        ("ī", "i"),
        ("ï", "i"),
        ("ū", "u"),
        ("ō", "o"),
        ("ē", "e"),
        ("š", "sh"),
        ("ḥ", "h"),
        ("ṭ", "t"),
        ("ṣ", "s"),
        ("ḍ", "d"),
        ("ẓ", "z"),
        ("ɣ", "gh"),
        ("θ", "th"),
        ("ð", "dh"),
        ("ʕ", ""),
        ("ʔ", ""),
        ("ʾ", ""),
        ("ʿ", ""),
        ("ˤ", ""),
        ("’", ""),
        ("'", ""),
        ("-", ""),
        (" ", ""),
        ("?", ""),
        ("؟", ""),
    ):
        folded = folded.replace(src, dst)
    folded = folded.replace("ee", "i").replace("oo", "u").replace("ou", "u")
    folded = folded.replace("e", "i").replace("o", "u")
    out: list[str] = []
    for char in folded:
        if not char.isalpha():
            continue
        if out and out[-1] == char:
            continue
        out.append(char)
    return "".join(out)


def _drop_edge(text: str) -> str:
    """Levantine often drops a leading qaf or a hamza at the edge, not one in the middle."""
    if text[:1] in {"q", "ʔ"}:
        text = text[1:]
    if text[-1:] in {"q", "ʔ"}:
        text = text[:-1]
    return text


def match_score(arabizi: str, arabic: str, translit: str = "") -> float:
    """How close this Arabic form is to the learner's Arabizi. 1 is the same consonants."""
    left = arabizi_skeleton(arabizi)
    scores = []
    if left:
        for right in arabic_skeletons(arabic):
            scores.append(_ratio(left, right))
            folded_left = _drop_edge(left)
            folded_right = _drop_edge(right)
            if folded_left and folded_right and (folded_left != left or folded_right != right):
                scores.append(_ratio(folded_left, folded_right))
    if translit:
        scores.append(_ratio(_loose(arabizi), _loose(translit)))
    return max(scores) if scores else 0.0


def _split_args(inner: str) -> list[str]:
    return [part.strip() for part in inner.split("|")]


def _line_label(line: str) -> str:
    head = line.split("{{", 1)[0]
    return head.lstrip("*#: ").strip().rstrip(":").strip().casefold()


def translation_candidates(wikitext: str) -> list[dict]:
    """Arabic forms cited on an English Wiktionary translation list."""
    found: list[dict] = []
    for line in (wikitext or "").splitlines():
        label = _line_label(line)
        levantine = "levantine" in label
        for match in _TEMPLATE.finditer(line):
            parts = _split_args(match.group(1))
            if len(parts) < 2:
                continue
            code = parts[0].strip().casefold()
            if code not in {"ar", "arz", "apc", "ajp"}:
                continue
            word = parts[1].strip()
            translit = ""
            for part in parts[2:]:
                if part.startswith("alt="):
                    word = part[4:].strip()
                elif part.startswith("tr="):
                    translit = part[3:].strip()
            arabic = clean_arabic(word)
            if not arabic:
                continue
            if not levantine and code in {"apc", "ajp"} and "mesopotamian" not in label:
                levantine = True
            found.append(
                {
                    "arabic": arabic,
                    "translit": translit,
                    "levantine": levantine,
                    "code": code,
                }
            )
    return found


def pick_translation(arabizi: str, wikitext: str) -> str | None:
    """The translation whose sound matches the Arabizi. Levantine beats a loose MSA guess."""
    ranked: list[tuple[float, bool, str]] = []
    for item in translation_candidates(wikitext):
        score = match_score(arabizi, item["arabic"], item["translit"])
        minimum = _LEVANT_MIN if item["levantine"] else _OTHER_MIN
        if score < minimum:
            continue
        ranked.append((score, bool(item["levantine"]), item["arabic"]))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return ranked[0][2]


def translation_hit(spelling: str, gloss: str, fetch) -> str | None:
    """Look the gloss up and keep the Arabic line that sounds like the Arabizi."""
    chunks: list[str] = []
    for head in gloss_heads(gloss):
        chunks.append(fetch(head) or "")
        extra = fetch(head + "/translations")
        if extra:
            chunks.append(extra)
        hit = pick_translation(spelling, "\n".join(chunks))
        if hit:
            return hit
    return None


def transliterate_arabizi(text: str) -> str:
    """One Arabic guess from the digit map, used only to ask Wiktionary if that page exists.

    Short vowels are mostly unwritten. This is not stored on its own: the
    Arabic page has to mention the English gloss first.
    """
    raw = (
        (text or "")
        .strip()
        .casefold()
        .replace("’", "'")
        .replace("‘", "'")
        .replace("`", "'")
    )
    words = []
    for word in raw.replace("-", "").split():
        letters = _transliterate_word(word)
        if letters:
            words.append(letters)
    return clean_arabic(" ".join(words))


def _transliterate_word(word: str) -> str:
    consonants = {
        "3'": "غ",
        "9'": "ض",
        "gh": "غ",
        "kh": "خ",
        "sh": "ش",
        "ch": "ش",
        "th": "ث",
        "dh": "ذ",
        "2": "ء",
        "3": "ع",
        "5": "خ",
        "6": "ط",
        "7": "ح",
        "8": "ق",
        "9": "ص",
        "b": "ب",
        "d": "د",
        "f": "ف",
        "g": "ج",
        "h": "ه",
        "j": "ج",
        "k": "ك",
        "l": "ل",
        "m": "م",
        "n": "ن",
        "q": "ق",
        "r": "ر",
        "s": "س",
        "t": "ت",
        "w": "و",
        "y": "ي",
        "z": "ز",
        "p": "ب",
        "'": "ء",
    }
    longs = {"aa": "ا", "ee": "ي", "ii": "ي", "oo": "و", "uu": "و"}
    out: list[str] = []
    index = 0
    while index < len(word):
        pair = word[index : index + 2]
        if pair in longs:
            out.append(longs[pair])
            index += 2
            continue
        if pair in consonants and not pair.isalpha():
            out.append(consonants[pair])
            index += 2
            continue
        if pair in consonants and pair in {"gh", "kh", "sh", "ch", "th", "dh"}:
            out.append(consonants[pair])
            index += 2
            continue
        char = word[index]
        if char in consonants:
            out.append(consonants[char])
        elif char in {"a", "e", "i", "o", "u"}:
            # A final vowel is often written; a short one in the middle is not.
            at_end = index == len(word) - 1
            at_start = not out
            if char == "a" and (at_end or at_start):
                out.append("ا")
            elif char in {"o", "u"} and (at_end or at_start or (out and out[-1] not in "اوي")):
                out.append("و")
            elif char in {"e", "i"} and at_end:
                out.append("ي")
            elif at_start and char in {"a", "e", "i"}:
                out.append("ا")
        index += 1
    if out and out[0] == "ء":
        out[0] = "أ"
    if out and out[0] == "ا":
        out[0] = "أ"
    return "".join(out)


def page_supports_gloss(wikitext: str, gloss: str) -> bool:
    """True when an Arabic entry's definitions use the learner's English word."""
    words = [
        word.casefold()
        for word in re.findall(r"[A-Za-z']+", gloss or "")
        if len(word) >= 3 and word.casefold() not in _STOP
    ]
    if not words:
        return False
    defs: list[str] = []
    for line in (wikitext or "").splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#") and not stripped.startswith(("#:", "##")):
            defs.append(stripped.casefold())
    blob = "\n".join(defs)
    if not blob:
        return False
    hits = sum(1 for word in words if re.search(rf"\b{re.escape(word)}\b", blob))
    return hits >= 1 and hits * 2 >= len(words)


def confirmed_transliteration(spelling: str, gloss: str, fetch) -> str | None:
    """Ask Wiktionary whether the Arabizi's Arabic guess is really this gloss."""
    candidate = transliterate_arabizi(spelling)
    skeleton = arabizi_skeleton(spelling).replace("ʔ", "")
    if not candidate or len(skeleton) < 2:
        return None
    page = fetch(candidate) or ""
    if page_supports_gloss(page, gloss):
        return candidate
    return None


def dictionary_arabic(spelling: str, gloss: str, fetch) -> str | None:
    """Arabic script from Wiktionary, or None when nothing there matches."""
    hit = translation_hit(spelling, gloss, fetch)
    if hit:
        return hit
    return confirmed_transliteration(spelling, gloss, fetch)


def _ai_prompt(rows: list[dict]) -> str:
    lines = [f'{row["id"]}\t{row["spelling"]}\t{row["gloss"]}' for row in rows]
    return (
        "Write the Levantine Arabic (Syrian or Lebanese) spelling in Arabic script.\n"
        "Use the Arabizi and the English gloss together. Prefer the colloquial word "
        "when it differs from Modern Standard (بيحكوا, not يتحدثون).\n"
        "Arabizi digits: 2 is ء or أ, 3 is ع, 3' is غ, 5 is خ, 6 is ط, 7 is ح, 8 is ق, "
        "9 is ص, 9' is ض. Long ee and oo stay long. كيفك is keefak.\n"
        "A hyphen can mark a prefix or a clitic (b-y-a7ko is بيحكوا).\n"
        "Return one Arabic spelling per id. Arabic script only.\n"
        "Items are tab-separated: id, Arabizi, English.\n"
        + "\n".join(lines)
    )


def ai_spellings(rows: list[dict], complete_fn, api_key: str) -> dict[str, str]:
    """One model call for a small batch. Keys are the string ids sent in the prompt."""
    if not rows or not api_key:
        return {}
    body = _json_body(_ai_prompt(rows), "arabic_script", _AI_SCHEMA, temperature=0)
    payload = complete_fn(body, api_key, pace=_LLM_PACE)
    data = json.loads(message_text(payload))
    found: dict[str, str] = {}
    for item in data.get("items") or []:
        if not isinstance(item, dict):
            continue
        arabic = clean_arabic(str(item.get("arabic") or ""))
        if arabic:
            found[str(item.get("id") or "")] = arabic
    return found


class PageSource:
    """Wiktionary wikitext, cached on disk and fetched a batch at a time."""

    def __init__(self, conn=None, opener=urllib.request.urlopen, pace: RateLimiter | None = None, sleep=None):
        self.conn = conn
        self.opener = opener
        self.pace = pace or _DICT_PACE
        self.sleep = sleep or time.sleep
        self._memory: dict[str, str] = {}

    def prefetch(self, titles: list[str]) -> None:
        needed: list[str] = []
        seen: set[str] = set()
        for title in titles:
            key = _title_key(title)
            if not key or key in seen or key in self._memory:
                continue
            seen.add(key)
            cached = _cache_get(self.conn, "page\n" + key, _PAGE_TTL)
            if cached is None:
                needed.append(key)
            else:
                self._memory[key] = cached
        for start in range(0, len(needed), _TITLE_BATCH):
            chunk = needed[start : start + _TITLE_BATCH]
            try:
                fetched = _fetch_titles(chunk, self.opener, self.pace, self.sleep)
            except Exception:
                # Don't cache a failed request. The next run can try again.
                for title in chunk:
                    self._memory.setdefault(title, "")
                continue
            for title, text in fetched.items():
                self._memory[title] = text
                _cache_put(self.conn, "page\n" + title, text)

    def __call__(self, title: str) -> str:
        key = _title_key(title)
        if not key:
            return ""
        if key not in self._memory:
            self.prefetch([key])
        return self._memory.get(key, "")


def _title_key(title: str) -> str:
    return " ".join((title or "").replace("|", " ").replace("\n", " ").split()).casefold()


def _fetch_titles(titles: list[str], opener, pace: RateLimiter, sleep) -> dict[str, str]:
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "prop": "revisions",
            "rvprop": "content",
            "rvslots": "main",
            "titles": "|".join(titles),
            "redirects": 1,
            "format": "json",
            "maxlag": 5,
        }
    )
    url = WIKTIONARY_API + "?" + params
    payload = _read_api(url, opener, pace, sleep)
    return _index_pages(payload, titles)


def _read_api(url: str, opener, pace: RateLimiter, sleep) -> dict:
    delay = 2.0
    last_error: Exception | None = None
    for attempt in range(4):
        pace.wait()
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        try:
            with opener(request, timeout=30) as response:
                payload = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 502, 503, 504} or attempt == 3:
                raise
            sleep(delay)
            delay = min(delay * 2, 30.0)
            continue
        error = payload.get("error") or {}
        if error.get("code") in {"maxlag", "ratelimited"} and attempt < 3:
            sleep(delay)
            delay = min(delay * 2, 30.0)
            continue
        return payload
    raise RuntimeError("Wiktionary lookup failed") from last_error


def _index_pages(payload: dict, requested: list[str]) -> dict[str, str]:
    query = payload.get("query") or {}
    by_title: dict[str, str] = {}
    for page in (query.get("pages") or {}).values():
        text = ""
        revisions = page.get("revisions") or []
        if revisions:
            slot = (revisions[0].get("slots") or {}).get("main") or {}
            text = slot.get("*") or slot.get("content") or ""
        by_title[(page.get("title") or "").casefold()] = text
    target: dict[str, str] = {}
    for item in query.get("normalized") or []:
        target[item.get("from", "").casefold()] = item.get("to", "").casefold()
    for item in query.get("redirects") or []:
        target[item.get("from", "").casefold()] = item.get("to", "").casefold()

    def final_name(name: str) -> str:
        seen: set[str] = set()
        current = name
        while current in target and current not in seen:
            seen.add(current)
            current = target[current]
        return current

    found: dict[str, str] = {}
    for title in requested:
        key = title.casefold()
        found[key] = by_title.get(final_name(key), by_title.get(key, ""))
    return found


def _cache_get(conn, key: str, ttl: timedelta | None):
    if conn is None:
        return None
    try:
        row = conn.execute(
            "SELECT payload, fetched_at FROM script_cache WHERE cache_key = ?",
            (key,),
        ).fetchone()
    except Exception:
        return None
    if row is None:
        return None
    if ttl is not None:
        try:
            fetched = datetime.strptime(row["fetched_at"][:19], "%Y-%m-%dT%H:%M:%S").replace(
                tzinfo=timezone.utc
            )
        except (TypeError, ValueError):
            return None
        if datetime.now(timezone.utc) - fetched > ttl:
            return None
    return row["payload"]


def _cache_put(conn, key: str, payload: str) -> None:
    if conn is None:
        return
    try:
        conn.execute(
            """
            INSERT INTO script_cache (cache_key, payload, fetched_at)
            VALUES (?, ?, ?)
            ON CONFLICT (cache_key) DO UPDATE SET
                payload = excluded.payload,
                fetched_at = excluded.fetched_at
            """,
            (key, payload, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")),
        )
        conn.commit()
    except Exception:
        return


def _result_key(spelling: str, gloss: str) -> str:
    return "result\n" + normalize_word(spelling) + "\n" + normalize_meaning(gloss)


def resolve_rows(conn, rows: list[dict], *, opener=urllib.request.urlopen, complete_fn=None, api_key: str | None = None, pace=None) -> list[dict]:
    """Dictionary first, then one model call for whatever is still open.

    Network failures leave those rows unresolved so a later run can retry.
    """
    if not rows:
        return []
    pages = PageSource(conn, opener=opener, pace=pace)
    titles: list[str] = []
    for row in rows:
        for head in gloss_heads(row["gloss"]):
            titles.append(head)
            titles.append(head + "/translations")
    pages.prefetch(titles)

    resolved: list[dict] = []
    unmatched: list[dict] = []
    for row in rows:
        cached = _cached_result(conn, row["spelling"], row["gloss"])
        if cached:
            resolved.append({"id": row["id"], **cached})
            continue
        try:
            hit = translation_hit(row["spelling"], row["gloss"], pages)
        except Exception:
            hit = None
        if hit:
            resolved.append({"id": row["id"], "arabic": hit, "source": SOURCE_DICTIONARY})
            _remember(conn, row, hit, SOURCE_DICTIONARY)
        else:
            unmatched.append(row)

    still: list[dict] = []
    if unmatched:
        pages.prefetch([transliterate_arabizi(row["spelling"]) for row in unmatched])
        for row in unmatched:
            try:
                hit = confirmed_transliteration(row["spelling"], row["gloss"], pages)
            except Exception:
                hit = None
            if hit:
                resolved.append({"id": row["id"], "arabic": hit, "source": SOURCE_DICTIONARY})
                _remember(conn, row, hit, SOURCE_DICTIONARY)
            else:
                still.append(row)

    if still:
        key = api_key
        if key is None:
            try:
                key = read_api_key()
            except RuntimeError:
                key = ""
        if key:
            caller = complete_fn or complete
            try:
                suggested = ai_spellings(still, caller, key)
            except Exception:
                suggested = {}
            for row in still:
                arabic = suggested.get(str(row["id"])) or ""
                if arabic:
                    resolved.append({"id": row["id"], "arabic": arabic, "source": SOURCE_AI})
                    _remember(conn, row, arabic, SOURCE_AI)
    return resolved


def _cached_result(conn, spelling: str, gloss: str) -> dict | None:
    raw = _cache_get(conn, _result_key(spelling, gloss), None)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    arabic = clean_arabic(data.get("arabic") or "")
    source = data.get("source") or ""
    if arabic and source in {SOURCE_DICTIONARY, SOURCE_AI}:
        return {"arabic": arabic, "source": source}
    return None


def _remember(conn, row: dict, arabic: str, source: str) -> None:
    _cache_put(conn, _result_key(row["spelling"], row["gloss"]), json.dumps({"arabic": arabic, "source": source}))


def _coerce_ids(value) -> list[int] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError("ids must be a list")
    ids: list[int] = []
    for item in value[:400]:
        try:
            ids.append(int(item))
        except (TypeError, ValueError):
            continue
    return ids


def pending_rows(conn, *, user_id: str | None = None, item_ids: list[int] | None = None, after_id: int = 0, limit: int | None = None) -> list[dict]:
    """Levantine rows with no Arabic spelling yet. User-typed spellings are not pending."""
    if item_ids is not None and not item_ids:
        return []
    clauses = [
        "l.language = 'arabic'",
        "i.arabic_script = ''",
        "COALESCE(i.arabic_source, '') != ?",
    ]
    params: list = [SOURCE_USER]
    if user_id:
        clauses.append("l.user_id = ?")
        params.append(user_id)
    if after_id:
        clauses.append("i.id > ?")
        params.append(after_id)
    if item_ids is not None:
        marks = ",".join("?" for _ in item_ids)
        clauses.append(f"i.id IN ({marks})")
        params.extend(item_ids)
    sql = f"""
        SELECT i.id, i.spelling, i.gloss, i.arabic_script, i.arabic_source
        FROM lesson_items i
        JOIN lessons l ON l.id = i.lesson_id
        WHERE {' AND '.join(clauses)}
        ORDER BY i.id
    """
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def apply_arabic(conn, resolutions: list[dict]) -> list[int]:
    """Write dictionary or model spellings. A user spelling and a filled row stay as they are."""
    wrote: list[int] = []
    with conn:
        for item in resolutions:
            arabic = clean_arabic(str(item.get("arabic") or ""))
            source = item.get("source") or ""
            if source not in {SOURCE_DICTIONARY, SOURCE_AI} or not arabic:
                continue
            cursor = conn.execute(
                """
                UPDATE lesson_items
                SET arabic_script = ?, arabic_source = ?
                WHERE id = ? AND arabic_script = '' AND COALESCE(arabic_source, '') != ?
                """,
                (arabic, source, int(item["id"]), SOURCE_USER),
            )
            if getattr(cursor, "rowcount", 0):
                wrote.append(int(item["id"]))
    return wrote


def fill_arabic_items(
    conn,
    *,
    user_id: str | None = None,
    item_ids=None,
    limit: int = 16,
    resolver=None,
) -> dict:
    """Fill a bounded batch. Pass resolver(rows) in tests to skip the network.

    Returns how many were written and which of the requested ids are still open.
    """
    ids = _coerce_ids(item_ids)
    rows = pending_rows(conn, user_id=user_id, item_ids=ids, limit=limit)
    if resolver is None:
        resolutions = resolve_rows(conn, rows)
    else:
        resolutions = list(resolver(rows) or [])
    wrote = apply_arabic(conn, resolutions)
    wrote_set = set(wrote)
    by_source = {SOURCE_DICTIONARY: 0, SOURCE_AI: 0}
    for item in resolutions:
        if int(item.get("id") or 0) in wrote_set and item.get("source") in by_source:
            by_source[item["source"]] += 1
    if ids is None:
        remaining = len(pending_rows(conn, user_id=user_id))
        remaining_ids: list[int] = []
    else:
        remaining_rows = pending_rows(conn, user_id=user_id, item_ids=ids)
        remaining = len(remaining_rows)
        remaining_ids = [row["id"] for row in remaining_rows]
    return {
        "filled": len(wrote),
        "dictionary": by_source[SOURCE_DICTIONARY],
        "ai": by_source[SOURCE_AI],
        "filled_ids": wrote,
        "remaining": remaining,
        "remaining_ids": remaining_ids,
    }


def backfill(conn, *, user_id: str | None = None, batch: int = 12, limit: int | None = None, resolver=None, verbose: bool = False) -> dict:
    """Walk every open Levantine row once. A second call skips rows already filled.

    The cursor moves by id, so a row the dictionary and the model both miss
    does not block the rows after it. Run the command again later to retry those.
    """
    stats = {"filled": 0, "dictionary": 0, "ai": 0, "seen": 0}
    after_id = 0
    while True:
        room = None if not limit else limit - stats["filled"]
        if room is not None and room <= 0:
            break
        step = batch if room is None else min(batch, room)
        rows = pending_rows(conn, user_id=user_id, after_id=after_id, limit=step)
        if not rows:
            break
        after_id = int(rows[-1]["id"])
        stats["seen"] += len(rows)
        if resolver is None:
            resolutions = resolve_rows(conn, rows)
        else:
            resolutions = list(resolver(rows) or [])
        wrote = apply_arabic(conn, resolutions)
        wrote_set = set(wrote)
        stats["filled"] += len(wrote)
        for item in resolutions:
            if int(item.get("id") or 0) not in wrote_set:
                continue
            if item.get("source") == SOURCE_DICTIONARY:
                stats["dictionary"] += 1
            elif item.get("source") == SOURCE_AI:
                stats["ai"] += 1
        if verbose:
            print(
                f"filled {stats['filled']} "
                f"(dictionary {stats['dictionary']}, model {stats['ai']}), "
                f"through id {after_id}",
                flush=True,
            )
    stats["remaining"] = len(pending_rows(conn, user_id=user_id))
    return stats


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Fill Levantine Arabic script for saved words. Safe to run again."
    )
    parser.add_argument("--db", default="lexicon.db", help="SQLite file. Ignored when DATABASE_URL is set.")
    parser.add_argument("--user", default="", help="Only this account. Default: every account.")
    parser.add_argument("--batch", type=int, default=12)
    parser.add_argument("--limit", type=int, default=0, help="Stop after this many filled words. 0 means all.")
    args = parser.parse_args(argv)
    conn = open_db(args.db)
    try:
        stats = backfill(
            conn,
            user_id=args.user.strip() or None,
            batch=max(1, args.batch),
            limit=args.limit or None,
            verbose=True,
        )
    finally:
        conn.close()
    print(
        f"Arabic script: {stats['filled']} filled "
        f"(dictionary {stats['dictionary']}, model {stats['ai']}), "
        f"{stats['remaining']} still open."
    )


if __name__ == "__main__":
    main()
