"""Read the next Arabic lesson from a Google Calendar iCal feed.

The private calendar link stays in settings. Callers only receive the next
event whose title contains "arabic".
"""

from __future__ import annotations

import sqlite3
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

_CALENDAR_HOSTS = ("calendar.google.com",)


def save_calendar_url(conn: sqlite3.Connection, url: str) -> None:
    cleaned = url.strip()
    if not _allowed(cleaned):
        raise ValueError("paste the private iCal link from Google Calendar")
    with conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('calendar_url', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (cleaned,),
        )


def calendar_connected(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT value FROM settings WHERE key = 'calendar_url'").fetchone()
    return bool(row and row["value"])


def next_lesson(
    conn: sqlite3.Connection,
    now: datetime | None = None,
    fetch=None,
) -> dict | None:
    """The next future event titled as an Arabic lesson, or None."""
    row = conn.execute("SELECT value FROM settings WHERE key = 'calendar_url'").fetchone()
    if row is None or not row["value"]:
        return None
    if fetch is None:
        fetch = _fetch
    text = fetch(row["value"])
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    upcoming = [
        event
        for event in parse_events(text)
        if "arabic" in event["summary"].casefold() and event["start"] >= moment
    ]
    if not upcoming:
        return None
    upcoming.sort(key=lambda event: event["start"])
    chosen = upcoming[0]
    return {
        "summary": chosen["summary"],
        "start": chosen["start"].isoformat(),
    }


def parse_events(text: str) -> list[dict]:
    events = []
    for block in _unfold(text).split("BEGIN:VEVENT"):
        if "END:VEVENT" not in block:
            continue
        body = block.split("END:VEVENT", 1)[0]
        fields: dict[str, str] = {}
        for line in body.splitlines():
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            fields[name.split(";", 1)[0]] = value.replace("\\n", " ").replace("\\,", ",")
        if "DTSTART" not in fields or "SUMMARY" not in fields:
            continue
        start = _parse_start(body, fields["DTSTART"])
        if start is None:
            continue
        events.append({"summary": fields["SUMMARY"].strip(), "start": start})
    return events


def _parse_start(body: str, value: str) -> datetime | None:
    raw_line = ""
    for line in body.splitlines():
        if line.startswith("DTSTART"):
            raw_line = line
            break
    if "VALUE=DATE" in raw_line and "T" not in value:
        try:
            day = datetime.strptime(value, "%Y%m%d")
        except ValueError:
            return None
        return day.replace(tzinfo=timezone.utc)
    zone = None
    if "TZID=" in raw_line:
        zone_name = raw_line.split("TZID=", 1)[1].split(":", 1)[0]
        try:
            zone = ZoneInfo(zone_name)
        except Exception:
            zone = None
    stamp = value.replace("Z", "")
    try:
        parsed = datetime.strptime(stamp, "%Y%m%dT%H%M%S")
    except ValueError:
        return None
    if value.endswith("Z"):
        return parsed.replace(tzinfo=timezone.utc)
    if zone is not None:
        return parsed.replace(tzinfo=zone).astimezone(timezone.utc)
    return parsed.replace(tzinfo=timezone.utc)


def _unfold(text: str) -> str:
    lines = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith((" ", "\t")) and lines:
            lines[-1] += line[1:]
        else:
            lines.append(line)
    return "\n".join(lines)


def _allowed(url: str) -> bool:
    if not url.startswith("https://"):
        return False
    host = url.split("/", 3)[2]
    return host in _CALENDAR_HOSTS or host.endswith(".calendar.google.com")


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "leventine-notebook"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise RuntimeError("could not read the calendar") from exc
