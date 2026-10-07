import type { ChecklistItem, LearningLanguage, NotebookItem, TalkReply } from "./types";

export function normalizeLearningLanguage(value: string | null | undefined): LearningLanguage {
  const raw = (value || "").toLowerCase();
  if (raw === "japanese" || raw === "ja" || raw === "romaji") return "japanese";
  return "arabic";
}

export function micLocale(language: LearningLanguage): string {
  return language === "japanese" ? "ja-JP" : "ar-SA";
}

export function isJapaneseText(text: string): boolean {
  return /[\u3040-\u30ff\u3400-\u9fff]/.test(text || "");
}

export function looksLikeLevantine(text: string): boolean {
  const line = text || "";
  if (/[2356789]/.test(line)) return true;
  if (/[\u0600-\u06FF]/.test(line)) return true;
  return /\b(keefak|kifak|ahlan|ahla|mar7aba|marhaba|ahwe|baddi|feek|yalla|habibi|shukran)\b/i.test(line);
}

export function assertReplyMatchesLearning(language: LearningLanguage, reply: TalkReply): void {
  if (language !== "japanese") return;
  const blob = [reply.arabizi, reply.arabic, reply.better, reply.correction].join(" ");
  if (looksLikeLevantine(blob)) {
    throw new Error("Got Arabic instead of Japanese — tap talk again");
  }
  if (reply.arabizi && !isJapaneseText(reply.arabic || "")) {
    throw new Error("No Japanese script to speak. Type a line, or try again.");
  }
}

export function hasSpeechScript(language: LearningLanguage, text: string): boolean {
  if (language === "japanese") return /[\u3040-\u30ff\u3400-\u9fff]/.test(text || "");
  return /[\u0600-\u06FF]/.test(text || "");
}

export function isoDay(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

export function formatDay(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

export function formatLesson(iso: string): string {
  return new Date(iso).toLocaleString("en", {
    weekday: "long",
    day: "numeric",
    month: "long",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function groupByDate(items: NotebookItem[]): [string, NotebookItem[]][] {
  const groups = new Map<string, NotebookItem[]>();
  for (const item of items) {
    const rows = groups.get(item.learned_on);
    if (rows) rows.push(item);
    else groups.set(item.learned_on, [item]);
  }
  return [...groups.entries()];
}

export function recentLessons(items: NotebookItem[]): NotebookItem[][] {
  const ids: number[] = [];
  for (const item of items) {
    if (!ids.includes(item.lesson_id)) ids.push(item.lesson_id);
    if (ids.length === 3) break;
  }
  const kept = new Set(ids);
  const groups = new Map<number, NotebookItem[]>();
  for (const item of items) {
    if (!kept.has(item.lesson_id)) continue;
    const rows = groups.get(item.lesson_id);
    if (rows) rows.push(item);
    else groups.set(item.lesson_id, [item]);
  }
  return [...groups.values()];
}

export function normalizeChecklist(raw: unknown): ChecklistItem[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((item) => item && typeof item === "object")
    .map((item) => {
      const row = item as Partial<ChecklistItem>;
      return {
        id: String(row.id || randomId()),
        title: String(row.title || ""),
        description: String(row.description || ""),
        done: Boolean(row.done),
        open: Boolean(row.open),
      };
    });
}

export function randomId(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") return globalThis.crypto.randomUUID();
  return `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function sortChecklist(items: ChecklistItem[]): ChecklistItem[] {
  return [...items].sort((a, b) => Number(a.done) - Number(b.done));
}

export function checklistStorageKey(language: LearningLanguage): string {
  return `checklist:${language}`;
}

export function cleanServerUrl(value: string): string {
  return value.trim().replace(/\/+$/, "");
}

export function decodeBase64(b64: string): Uint8Array {
  const clean = b64.replace(/\s/g, "");
  const binary = globalThis.atob(clean);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

export function correctionNote(
  language: LearningLanguage,
  said: string,
  reply: TalkReply,
  tryPrefix: string,
): string {
  const spokeNative = language === "japanese" && isJapaneseText(said);
  return [
    reply.correction,
    reply.better &&
      (!spokeNative || reply.better !== reply.you_arabizi) &&
      tryPrefix + reply.better,
  ]
    .filter(Boolean)
    .join(" ");
}
