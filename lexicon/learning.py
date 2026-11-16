"""Teacher lessons, sentence work, and knowledge recall. Cards keep their FSRS."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timedelta, timezone

from lexicon.db import insert_id
from lexicon.intake import item_kind, parse_lesson_text
from lexicon.load import normalize_meaning, normalize_word
from lexicon.prefs import get_language

GUIDE = [
    {"id": "past", "title": "Completed actions · perfect", "explanation": "Use the perfect for an action presented as completed. Learn the person endings with the verb rather than translating every English past construction mechanically.", "prompt": "Describe something you finished yesterday using a word from your latest lesson.", "source": "Levantine Arabic Verbs · pp. 107–108"},
    {"id": "imperfect", "title": "Bare imperfect · after another verb", "explanation": "The bare imperfect often follows words for wanting, being able to, and other auxiliaries. It also participates in future and continuous constructions. Keep it separate from the b-present.", "prompt": "Say what you want or are able to do, then explain why the second verb has no b-prefix.", "source": "Levantine Arabic Verbs · pp. 108–110"},
    {"id": "present", "title": "Habits · b-present", "explanation": "The bi-imperfect commonly describes habits and general facts. Person prefixes and the we form vary. Record the form your teacher uses for each subject.", "prompt": "Describe a habit, then contrast it with something happening right now.", "source": "Levantine Arabic Verbs · pp. 110–111"},
    {"id": "continuous", "title": "Happening now · 3am + imperfect", "explanation": "The progressive particle 3am (عم) usually precedes the bare imperfect to describe an ongoing action. This is a construction, not a new noun or a universal replacement for every English -ing form.", "prompt": "Describe what two people are doing now using two of your lesson words.", "source": "Levantine Arabic Verbs · pp. 109–111"},
    {"id": "future", "title": "Plans · ra7 + imperfect", "explanation": "A future particle such as ra7 can precede the imperfect. Add the person form you learned, and keep a negative example alongside a positive one.", "prompt": "Give a plan for tomorrow, then say one thing you will not do.", "source": "Levantine Arabic Verbs · p. 109"},
    {"id": "imperative", "title": "Requests and commands · imperative", "explanation": "Learn masculine, feminine, and plural commands separately when useful. Positive command vowels can be unpredictable. Negative commands use a different construction with ma and a second-person imperfect.", "prompt": "Ask one person to do something, then politely tell them not to do something else.", "source": "Levantine Arabic Verbs · p. 112"},
    {"id": "participle", "title": "States · active participle", "explanation": "An active participle behaves like an adjective in gender and number. Depending on the verb and context it can express a state, result, or other meaning. It is not automatically equivalent to English continuous tense.", "prompt": "Explain a state or result using a participle your teacher confirmed.", "source": "Levantine Arabic Verbs · pp. 113–114"},
    {"id": "family", "title": "Word families · meaning and form", "explanation": "Keep related nouns, verbal nouns, adjectives, and verbs together, but preserve each meaning. Sharing a root does not guarantee that a form is used or means what an English derivation suggests.", "prompt": "Use a noun and a related verb in different sentences and explain the difference.", "source": "Word-family study · teacher confirmation recommended"},
]


def now():
    return datetime.now(timezone.utc).isoformat()


def text(value, name, *, required=False, limit=12000):
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    value = value.strip()
    if required and not value:
        raise ValueError(f"Add {name}")
    if len(value) > limit:
        raise ValueError(f"{name} is too long")
    return value


def day(value, name="date", *, optional=False):
    value = text(value, name)
    if optional and not value:
        return ""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValueError(f"Choose a valid {name}") from None


def number(value, name, low=1, high=1000000000):
    if isinstance(value, bool):
        raise ValueError(f"Invalid {name}")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"Invalid {name}")
    try:
        result = int(value)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid {name}") from None
    if result < low or result > high:
        raise ValueError(f"Invalid {name}")
    return result


def owned(conn, table, record_id, user_id, language=None):
    # table comes only from this module's fixed call sites.
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ? AND user_id = ?", (number(record_id, "record"), user_id)).fetchone()
    if row is None or (language and row["language"] != language):
        raise LookupError("That record is not in this notebook")
    return dict(row)


def _decode(row, fields):
    result = dict(row)
    for field in fields:
        result[field] = json.loads(result[field])
    return result


def _words(conn, user_id, language):
    return [dict(row) for row in conn.execute(
        """SELECT i.id, i.spelling, i.gloss, i.arabic_script, i.arabic_source
        FROM lesson_items i JOIN lessons l ON l.id = i.lesson_id
        WHERE l.user_id = ? AND l.language = ? ORDER BY i.id DESC""", (user_id, language)).fetchall()]


def _word_selection(conn, user_id, language, ids):
    if not isinstance(ids, list) or len(ids) > 100:
        raise ValueError("Choose up to 100 required words")
    available = {row["id"]: row for row in reversed(_words(conn, user_id, language))}
    result = []
    for item_id in dict.fromkeys(number(value, "word") for value in ids):
        if item_id not in available:
            raise LookupError("A required word is not in this notebook")
        result.append(available[item_id])
    return result


def _rule_selection(conn, user_id, language, ids):
    if not isinstance(ids, list) or len(ids) > 12:
        raise ValueError("Choose up to 12 grammar rules")
    return [owned(conn, "learning_rules", value, user_id, language) for value in dict.fromkeys(number(value, "rule") for value in ids)]


def workspace(conn, user_id):
    language = get_language(conn, user_id)
    sessions = [_decode(row, ["words"]) for row in conn.execute("SELECT * FROM learning_sessions WHERE user_id = ? AND language = ? ORDER BY learned_on DESC,id DESC LIMIT 200", (user_id, language)).fetchall()]
    rules = [dict(row) for row in conn.execute("SELECT * FROM learning_rules WHERE user_id = ? AND language = ? ORDER BY due_on,id DESC LIMIT 500", (user_id, language)).fetchall()]
    tasks = [_decode(row, ["words", "rules"]) for row in conn.execute("SELECT * FROM learning_tasks WHERE user_id = ? AND language = ? ORDER BY created_at DESC,id DESC LIMIT 200", (user_id, language)).fetchall()]
    teacher = conn.execute("SELECT value FROM settings WHERE user_id = ? AND key = 'learning_teacher'", (user_id,)).fetchone()
    return {"language": language, "teacher": teacher["value"] if teacher else "", "sessions": sessions, "rules": rules, "tasks": tasks,
            "due_rules": [rule for rule in rules if rule["due_on"] <= date.today().isoformat()], "guide": GUIDE if language == "arabic" else [],
            "counts": {"sessions": len(sessions), "open_homework": sum(task["status"] == "open" for task in tasks), "rules": len(rules)}}


def task_detail(conn, user_id, task_id):
    language = get_language(conn, user_id)
    task = _decode(owned(conn, "learning_tasks", task_id, user_id, language), ["words", "rules"])
    attempts = [_decode(row, ["requirements"]) for row in conn.execute("SELECT * FROM learning_attempts WHERE task_id = ? AND user_id = ? ORDER BY id DESC LIMIT 100", (task["id"], user_id)).fetchall()]
    for attempt in attempts:
        attempt["corrections"] = [dict(row) for row in conn.execute("SELECT * FROM learning_corrections WHERE attempt_id = ? AND user_id = ? ORDER BY id", (attempt["id"], user_id)).fetchall()]
    task["attempts"] = attempts
    return task


def rule_detail(conn, user_id, rule_id):
    rule = owned(conn, "learning_rules", rule_id, user_id, get_language(conn, user_id))
    rule["history"] = [_decode(row, ["rule_snapshot"]) for row in conn.execute("SELECT * FROM learning_recalls WHERE rule_id = ? AND user_id = ? ORDER BY id DESC LIMIT 100", (rule["id"], user_id)).fetchall()]
    return rule


def dispatch_get(conn, user_id, action, record_id=""):
    if action == "workspace":
        return workspace(conn, user_id)
    if action == "task":
        return task_detail(conn, user_id, record_id)
    if action == "rule":
        return rule_detail(conn, user_id, record_id)
    raise ValueError("Unknown notebook view")


def dispatch_post(conn, user_id, body):
    if not isinstance(body, dict):
        raise ValueError("Send a notebook action")
    action = body.get("action", "")
    if action not in {"capture", "rule", "task", "draft", "attempt", "correction", "recall", "task-status"}:
        raise ValueError("Unknown notebook action")
    request_id = text(body.get("request_id", str(uuid.uuid4())), "request key", required=True, limit=100)
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    previous = conn.execute("SELECT digest,result FROM learning_receipts WHERE user_id = ? AND request_id = ?", (user_id, request_id)).fetchone()
    if previous:
        if previous["digest"] != digest:
            raise ValueError("This save key was already used for different content")
        return json.loads(previous["result"])
    language = get_language(conn, user_id)
    with conn:
        result = _write(conn, user_id, language, action, body)
        conn.execute("INSERT INTO learning_receipts(user_id,request_id,digest,result) VALUES (?,?,?,?)", (user_id, request_id, digest, json.dumps(result)))
    return result


def _new_rule(conn, user_id, language, body, session_id=None):
    title = text(body.get("title", ""), "rule title", required=True, limit=200)
    explanation = text(body.get("explanation", ""), "rule explanation", required=True)
    example = text(body.get("example", ""), "example", limit=4000)
    source = text(body.get("source", "Teacher lesson"), "source", limit=400)
    return insert_id(conn, "INSERT INTO learning_rules(user_id,language,session_id,title,explanation,example,source,due_on,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (user_id, language, session_id, title, explanation, example, source, date.today().isoformat(), now()))


def _new_task(conn, user_id, language, body, session_id=None, words=None, rules=None):
    if words is None:
        words = _word_selection(conn, user_id, language, body.get("word_ids", []))
    if rules is None:
        rules = _rule_selection(conn, user_id, language, body.get("rule_ids", []))
    count = number(body.get("sentence_count", 3), "sentence count", high=30)
    prompt = text(body.get("prompt", ""), "homework", limit=6000)
    if not prompt:
        prompt = f"Write {count} original sentences about {body.get('goal') or 'something from your own life'}. Use the selected lesson words"
        prompt += " and apply " + ", ".join(rule["title"] for rule in rules) + "." if rules else ". Explain a grammar choice to your teacher."
    due = day(body.get("due_on", ""), "homework date", optional=True)
    return insert_id(conn, "INSERT INTO learning_tasks(user_id,language,session_id,prompt,words,rules,sentence_count,due_on,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (user_id, language, session_id, prompt, json.dumps(words), json.dumps(rules), count, due, now()))


def _capture(conn, user_id, language, body):
    title = text(body.get("title", ""), "lesson title", required=True, limit=200)
    learned_on = day(body.get("learned_on", ""))
    teacher = text(body.get("teacher", ""), "teacher", limit=200)
    goal = text(body.get("goal", ""), "practice goal", limit=2000)
    notes = text(body.get("notes", ""), "lesson notes")
    raw = text(body.get("words_text", ""), "vocabulary", limit=18000)
    pairs = parse_lesson_text(raw, language=language) if raw else []
    if raw and not pairs:
        raise ValueError("Add vocabulary as word = meaning, or leave Words empty for a grammar lesson")
    if len(pairs) > 100:
        raise ValueError("Capture up to 100 words per lesson. Use CSV import for larger lists.")
    specs = body.get("rules", [])
    if not isinstance(specs, list) or len(specs) > 12 or any(not isinstance(spec, dict) for spec in specs):
        raise ValueError("Add up to 12 grammar rules")
    # Validate the task and rule fields before any writes.
    for spec in specs:
        text(spec.get("title", ""), "rule title", required=True, limit=200)
        text(spec.get("explanation", ""), "rule explanation", required=True)
    number(body.get("sentence_count", 3), "sentence count", high=30)
    day(body.get("due_on", ""), "homework date", optional=True)
    selected = _word_selection(conn, user_id, language, body.get("word_ids", []))
    existing = {(normalize_word(row["spelling"]), normalize_meaning(row["gloss"])): row for row in reversed(_words(conn, user_id, language))}
    import_id = None
    for spelling, gloss in pairs:
        key = (normalize_word(spelling), normalize_meaning(gloss))
        if key not in existing:
            if import_id is None:
                import_id = insert_id(conn, "INSERT INTO lessons(user_id,language,learned_on,raw_text,created_at) VALUES (?,?,?,?,?)", (user_id, language, learned_on, raw, now()))
            item_id = insert_id(conn, "INSERT INTO lesson_items(lesson_id,position,spelling,gloss,kind) VALUES (?,?,?,?,?)", (import_id, len(existing), spelling, gloss, item_kind(spelling)))
            existing[key] = {"id": item_id, "spelling": spelling, "gloss": gloss, "arabic_script": "", "arabic_source": ""}
        if existing[key]["id"] not in {word["id"] for word in selected}:
            selected.append(existing[key])
    session_id = insert_id(conn, "INSERT INTO learning_sessions(user_id,language,learned_on,title,teacher,goal,notes,words,created_at) VALUES (?,?,?,?,?,?,?,?,?)", (user_id, language, learned_on, title, teacher, goal, notes, json.dumps(selected), now()))
    rule_ids = [_new_rule(conn, user_id, language, spec, session_id) for spec in specs]
    rule_ids += [rule["id"] for rule in _rule_selection(conn, user_id, language, body.get("rule_ids", []))]
    rules = _rule_selection(conn, user_id, language, rule_ids)
    task_id = _new_task(conn, user_id, language, body, session_id, selected, rules)
    conn.execute("INSERT INTO settings(user_id,key,value) VALUES (?,'learning_teacher',?) ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value", (user_id, teacher))
    return {"session_id": session_id, "task_id": task_id, "word_ids": [word["id"] for word in selected], "rule_ids": rule_ids}


def _write(conn, user_id, language, action, body):
    if action == "capture":
        return _capture(conn, user_id, language, body)
    if action == "rule":
        return {"rule_id": _new_rule(conn, user_id, language, body)}
    if action == "task":
        session_id = body.get("session_id")
        if session_id is not None:
            session_id = owned(conn, "learning_sessions", session_id, user_id, language)["id"]
        return {"task_id": _new_task(conn, user_id, language, body, session_id)}
    if action in {"draft", "attempt", "task-status"}:
        task = owned(conn, "learning_tasks", body.get("task_id"), user_id, language)
        if action == "task-status":
            status = body.get("status")
            if status not in {"open", "done"}:
                raise ValueError("Choose open or done")
            conn.execute("UPDATE learning_tasks SET status = ? WHERE id = ?", (status, task["id"]))
            return {"status": status}
        answer = text(body.get("text", ""), "your sentences", required=action == "attempt")
        revision = number(body.get("revision"), "draft revision", low=0)
        updated = conn.execute("UPDATE learning_tasks SET draft = ?, revision = revision + 1 WHERE id = ? AND revision = ?", (answer, task["id"], revision))
        if updated.rowcount != 1:
            raise ValueError("This draft changed on another device. Your text is still here. Copy it before reloading the saved draft.")
        result = {"revision": revision + 1, "saved_at": now()}
        if action == "attempt":
            requirements = {"words": json.loads(task["words"]), "rules": json.loads(task["rules"]), "prompt": task["prompt"], "sentence_count": task["sentence_count"]}
            result["attempt_id"] = insert_id(conn, "INSERT INTO learning_attempts(user_id,task_id,text,requirements,created_at) VALUES (?,?,?,?,?)", (user_id, task["id"], answer, json.dumps(requirements), now()))
        return result
    if action == "correction":
        attempt = owned(conn, "learning_attempts", body.get("attempt_id"), user_id)
        owned(conn, "learning_tasks", attempt["task_id"], user_id, language)
        correction = text(body.get("text", ""), "corrected sentences", required=True)
        note = text(body.get("note", ""), "correction explanation")
        author = text(body.get("author", "Teacher notes entered by me"), "correction source", required=True, limit=200)
        return {"correction_id": insert_id(conn, "INSERT INTO learning_corrections(user_id,attempt_id,text,note,author,created_at) VALUES (?,?,?,?,?,?)", (user_id, attempt["id"], correction, note, author, now()))}
    if action == "recall":
        rule = owned(conn, "learning_rules", body.get("rule_id"), user_id, language)
        response = text(body.get("response", ""), "recall answer", required=True, limit=6000)
        rating = body.get("rating")
        if rating not in {"again", "partly", "recalled"}:
            raise ValueError("Choose a recall rating")
        due = (date.today() + timedelta(days={"again": 1, "partly": 3, "recalled": 7}[rating])).isoformat()
        recall_id = insert_id(conn, "INSERT INTO learning_recalls(user_id,rule_id,response,rating,rule_snapshot,created_at) VALUES (?,?,?,?,?,?)", (user_id, rule["id"], response, rating, json.dumps(rule), now()))
        conn.execute("UPDATE learning_rules SET due_on = ? WHERE id = ?", (due, rule["id"]))
        return {"recall_id": recall_id, "due_on": due}
    raise ValueError("Unknown notebook action")
