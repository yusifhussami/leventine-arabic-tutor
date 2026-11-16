"""Refresh Arwords' public word index and match it against a learner's notebook."""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
import unicodedata
import urllib.request
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

INDEX = "https://www.arwords.com/words/index"
DATA = Path(__file__).with_name("arwords_index.json")
AGENT = "Sawt/1.0 (https://github.com/yusifhussami/leventine-arabic-tutor)"


def _write_json(path, payload):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    temporary.replace(path)


class IndexParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.cells = None
        self.cell = None
        self.href = ""
        self.next_url = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.cells = []
            self.href = ""
        elif tag == "td" and self.cells is not None:
            self.cell = []
        elif tag == "a":
            href = attrs.get("href", "")
            if re.fullmatch(r"/words/view/\d+", href):
                self.href = href
            elif re.fullmatch(r"/words/index/\d+", href):
                self.link = href
                self.link_text = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)
        if getattr(self, "link", ""):
            self.link_text.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.cells.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr":
            if self.href and self.cells and len(self.cells) >= 2:
                self.rows.append({"arabic": self.cells[0], "meaning": self.cells[1], "url": urljoin(INDEX, self.href)})
            self.cells = None
        elif tag == "a" and getattr(self, "link", ""):
            if "".join(self.link_text).strip() == "Next":
                self.next_url = urljoin(INDEX, self.link)
            self.link = ""


class FormsParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self.row = None
        self.field = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.row = {}
        if self.row is not None:
            field = {"ar_word_form": "arabic", "chat_view": "translit", "form_dialect": "dialect", "form_conj": "conjugation"}.get(attrs.get("class"))
            if field:
                self.field = field
                self.row[field] = ""

    def handle_data(self, data):
        if self.row is not None and self.field:
            self.row[self.field] += data

    def handle_endtag(self, tag):
        if tag in {"span", "td"}:
            self.field = None
        if tag == "tr" and self.row is not None:
            if self.row.get("arabic") and self.row.get("translit"):
                self.forms.append({k: v.strip() for k, v in self.row.items()})
            self.row = None


def enrich_csv(input_path, *, delay=0.5):
    """Cache the listed forms of dictionary entries relevant to this CSV."""
    from lexicon.arabic_script import match_score

    payload = json.loads(DATA.read_text())
    by_url = {entry["url"]: entry for entry in payload["entries"]}
    with open(input_path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    candidates = {}
    for row in rows:
        for gloss in re.split(r"[;/|]", row.get("Meaning", row.get("gloss", ""))):
            for entry in dictionary().get(meaning_key(gloss), []):
                if match_score(row.get("Word", row.get("spelling", "")), entry["arabic"]) >= 0.74:
                    candidates[entry["url"]] = entry
    for index, (url, entry) in enumerate(candidates.items(), 1):
        if "forms" in by_url[url]:
            continue
        request = urllib.request.Request(url, headers={"User-Agent": AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            parser = FormsParser()
            parser.feed(response.read().decode("utf-8"))
        by_url[url]["forms"] = parser.forms
        _write_json(DATA, payload)
        if index % 25 == 0:
            print(f"Forms: {index}/{len(candidates)} entries", flush=True)
        time.sleep(delay)
    dictionary.cache_clear()
    print(f"Forms complete: {len(candidates)} relevant entries", flush=True)


def refresh(path=DATA, *, delay=0.5):
    """One request at a time; checkpoint each page so an interrupted run resumes."""
    path = Path(path)
    checkpoint = path.with_suffix(".partial.json")
    payload = {"source": INDEX, "entries": [], "next": INDEX, "pages": 0}
    if checkpoint.exists():
        payload = json.loads(checkpoint.read_text())
    seen = {entry["url"] for entry in payload["entries"]}
    while payload["next"]:
        url = payload["next"]
        request = urllib.request.Request(url, headers={"User-Agent": AGENT})
        with urllib.request.urlopen(request, timeout=30) as response:
            parser = IndexParser()
            parser.feed(response.read().decode("utf-8"))
        if not parser.rows:
            raise ValueError(f"No entries on {url}; retaining checkpoint")
        if parser.next_url == url:
            raise ValueError("Index pagination did not advance")
        for entry in parser.rows:
            if entry["url"] not in seen:
                payload["entries"].append(entry)
                seen.add(entry["url"])
        payload["next"] = parser.next_url
        payload["pages"] += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_json(checkpoint, payload)
        if payload["pages"] % 25 == 0:
            print(f"{payload['pages']} pages, {len(seen)} words", flush=True)
        if payload["next"]:
            time.sleep(delay)
    _write_json(path, payload)
    checkpoint.unlink()
    print(f"Complete: {payload['pages']} pages, {len(seen)} words", flush=True)


def meaning_key(text):
    text = re.sub(r"\[[^]]*\]|\([^)]*\)", " ", text.casefold())
    return " ".join(word for word in re.findall(r"[a-z']+", text) if word not in {"a", "an", "the", "to"})


@lru_cache(maxsize=1)
def dictionary():
    if not DATA.exists():
        return {}
    entries = json.loads(DATA.read_text())["entries"]
    by_meaning = {}
    for entry in entries:
        for meaning in re.split(r"[;/|]", entry["meaning"]):
            key = meaning_key(meaning)
            if key:
                by_meaning.setdefault(key, []).append(entry)
    return by_meaning


def match(spelling, gloss, *, entries=None):
    from lexicon.arabic_script import clean_arabic, match_score

    source = dictionary() if entries is None else entries
    candidates = {}
    spellings = {}
    for meaning in re.split(r"[;/|]", gloss):
        for entry in source.get(meaning_key(meaning), []):
            # Listed forms distinguish inflections which share consonants.
            forms = entry.get("forms")
            choices = forms if forms is not None else [{"arabic": entry["arabic"]}]
            for form in choices:
                if form.get("dialect") and form["dialect"] not in {"Leb.", "Syr.", "Pal."}:
                    continue
                script = clean_arabic(form["arabic"])
                score = match_score(spelling, script)
                if forms is not None:
                    score = min(score, _form_score(spelling, form.get("translit", "")))
                if script and score >= 0.9:
                    canonical = "".join(c for c in script if unicodedata.category(c) != "Mn" and c != "ـ")
                    if score > candidates.get(canonical, 0):
                        candidates[canonical] = score
                        spellings[canonical] = script
    ranked = sorted(candidates, key=candidates.get, reverse=True)
    if not ranked or (len(ranked) > 1 and candidates[ranked[0]] - candidates[ranked[1]] < 0.12):
        return None
    return spellings[ranked[0]]


def _form_score(spelling, translit):
    from difflib import SequenceMatcher

    def normalize(text):
        # Arwords chat spelling uses w/y for vowels and Arabic final ة as h.
        text = text.casefold().replace("sh", "š").replace("kh", "5").replace("gh", "غ")
        text = text.replace("oo", "u").replace("ou", "u").replace("ee", "i").replace("aa", "a")
        text = text.replace("o", "u").replace("e", "i").replace("w", "u").replace("y", "i")
        text = re.sub(r"[^a-z0-9šغ]", "", text)
        text = re.sub(r"(.)\1+", r"\1", text)
        text = re.sub(r"^[28q]|[28q]$", "", text)
        return text.removesuffix("h")

    left, right = normalize(spelling), normalize(translit)
    score = SequenceMatcher(None, left, right).ratio()
    if score >= 0.9:
        return score
    # Chat spelling often omits short vowels (bas / bs). Explicit long-vowel
    # disagreements still reject a different form (koon / kaan).
    def long_vowels(text):
        return ["u" if vowel in {"oo", "uu", "ou"} else "i" if vowel in {"ee", "ii"} else "a"
                for vowel in re.findall(r"aa|ee|ii|oo|uu|ou", text.casefold())]
    left_long, right_long = long_vowels(spelling), long_vowels(translit)
    if left_long and right_long and left_long != right_long:
        return 0.0
    if not re.search(r"[aeiou]", right) and re.sub(r"[aeiou]", "", left) == right:
        return 0.95
    return score


def match_notebook(conn, user_id):
    """Reconcile this account's Arabic words without replacing manual edits."""
    from lexicon.arabic_script import clean_arabic

    rows = conn.execute(
        """SELECT i.id, i.spelling, i.gloss, i.arabic_script, i.arabic_source
        FROM lesson_items i JOIN lessons l ON l.id = i.lesson_id
        WHERE l.user_id = ? AND l.language = 'arabic'""", (user_id,)
    ).fetchall()
    matched = unchanged = unresolved = 0
    with conn:
        for row in rows:
            if row["arabic_source"] == "user":
                unchanged += 1
                continue
            hit = match(row["spelling"], row["gloss"])
            if not hit:
                unresolved += 1
                continue
            if clean_arabic(row["arabic_script"]) == hit and row["arabic_source"] == "arwords":
                unchanged += 1
                continue
            conn.execute("UPDATE lesson_items SET arabic_script = ?, arabic_source = 'arwords' WHERE id = ? AND COALESCE(arabic_source, '') != 'user'", (hit, row["id"]))
            matched += 1
    return {"matched": matched, "unchanged": unchanged, "unresolved": unresolved, "dictionary_entries": len({entry["url"] for group in dictionary().values() for entry in group})}


def match_csv(input_path, output_path):
    """Preserve the source columns and add Arabic, source, and review status."""
    if Path(input_path).resolve() == Path(output_path).resolve():
        raise ValueError("Choose a new output file to preserve the original CSV")
    with open(input_path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    aliases = {field.strip().casefold(): field for field in fields}
    word = next((aliases[key] for key in ("arabizi", "word", "spelling") if key in aliases), None)
    gloss = next((aliases[key] for key in ("meaning", "gloss", "english") if key in aliases), None)
    if not word or not gloss:
        raise ValueError("CSV needs Word/Arabizi and Meaning columns")
    for field in ("Arabic", "Arabic source", "Arabic match"):
        if field not in fields:
            fields.append(field)
    matched = 0
    for row in rows:
        if row.get("Arabic", "").strip():
            row["Arabic match"] = "Existing spelling kept"
            continue
        hit = match(row[word], row[gloss])
        row["Arabic"] = hit or ""
        row["Arabic source"] = _source_url(hit, row[gloss]) if hit else ""
        row["Arabic match"] = "Matched Arabizi and meaning" if hit else "Needs review: no confident Arwords match"
        matched += bool(hit)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return {"rows": len(rows), "matched": matched}


def _source_url(arabic, gloss):
    for meaning in re.split(r"[;/|]", gloss):
        for entry in dictionary().get(meaning_key(meaning), []):
            if entry["arabic"] == arabic or any(form["arabic"] == arabic for form in entry.get("forms", [])):
                return entry["url"]
    return INDEX


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DATA)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--matched-output", type=Path)
    parser.add_argument("--enrich-csv", type=Path)
    args = parser.parse_args()
    if args.enrich_csv:
        enrich_csv(args.enrich_csv, delay=max(0.5, args.delay))
    elif args.csv:
        if not args.matched_output:
            parser.error("--csv requires --matched-output")
        print(match_csv(args.csv, args.matched_output))
    else:
        refresh(args.output, delay=max(0.5, args.delay))
