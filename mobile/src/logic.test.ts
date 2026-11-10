import assert from "node:assert/strict";
import test from "node:test";

import {
  assertReplyMatchesLearning,
  checklistStorageKey,
  cleanServerUrl,
  correctionNote,
  decodeBase64,
  formatDay,
  groupByDate,
  normalizeChecklist,
  normalizeLearningLanguage,
  recentLessons,
  sortChecklist,
} from "./logic.ts";
import type { NotebookItem } from "./types.ts";

test("learning language aliases match the website", () => {
  assert.equal(normalizeLearningLanguage("ja"), "japanese");
  assert.equal(normalizeLearningLanguage("romaji"), "japanese");
  assert.equal(normalizeLearningLanguage("en"), "arabic");
  assert.equal(normalizeLearningLanguage(""), "arabic");
});

test("Japanese replies that slip into Arabic are rejected", () => {
  assert.throws(
    () => assertReplyMatchesLearning("japanese", { arabizi: "keefak", arabic: "كيفك" }),
    /Arabic instead of Japanese/,
  );
  assert.throws(
    () => assertReplyMatchesLearning("japanese", { arabizi: "mizu", arabic: "mizu" }),
    /No Japanese script/,
  );
  assert.doesNotThrow(() =>
    assertReplyMatchesLearning("japanese", { arabizi: "mizu", arabic: "水" }),
  );
});

test("lesson dates stay on the calendar day, not the previous UTC day", () => {
  assert.match(formatDay("2026-03-08"), /March/);
  assert.match(formatDay("2026-03-08"), /8/);
});

test("words group by lesson day and recent keeps three lessons", () => {
  const items: NotebookItem[] = [
    { id: 1, spelling: "a", gloss: "a", kind: "word", learned_on: "2026-03-08", lesson_id: 3 },
    { id: 2, spelling: "b", gloss: "b", kind: "word", learned_on: "2026-03-08", lesson_id: 3 },
    { id: 3, spelling: "c", gloss: "c", kind: "phrase", learned_on: "2026-03-01", lesson_id: 2 },
    { id: 4, spelling: "d", gloss: "d", kind: "word", learned_on: "2026-02-01", lesson_id: 1 },
    { id: 5, spelling: "e", gloss: "e", kind: "word", learned_on: "2026-01-01", lesson_id: 0 },
  ];
  const groups = groupByDate(items);
  assert.equal(groups.length, 4);
  assert.equal(groups[0][1].length, 2);
  const recent = recentLessons(items);
  assert.deepEqual(
    recent.map((rows) => rows[0].lesson_id),
    [3, 2, 1],
  );
});

test("checklist ticks sort open items ahead of done ones", () => {
  const items = sortChecklist(
    normalizeChecklist([
      { id: "1", title: "done", description: "", done: true, open: true },
      { id: "2", title: "open", description: "note", done: false, open: false },
    ]),
  );
  assert.equal(items[0].title, "open");
  assert.equal(items[0].open, false);
  assert.equal(checklistStorageKey("japanese"), "checklist:japanese");
});

test("server urls drop a trailing slash and wav bytes decode", () => {
  assert.equal(cleanServerUrl(" https://sawt.vercel.app/ "), "https://sawt.vercel.app");
  assert.equal(new TextDecoder().decode(decodeBase64("UklGRg==")), "RIFF");
});

test("a native-script Japanese line keeps a better suggestion", () => {
  const note = correctionNote(
    "japanese",
    "水",
    { correction: "Soften the vowel.", better: "mizu o kudasai", you_arabizi: "mizu" },
    "Try: ",
  );
  assert.match(note, /Soften the vowel/);
  assert.match(note, /Try: mizu o kudasai/);
});
