import { decodeBase64 } from "./logic";
import type { Judgment, NextLesson, NotebookItem, PreviewItem, ServerConfig, TalkReply } from "./types";

export type TokenGetter = () => Promise<string | null>;

export type Api = {
  request(path: string, init?: RequestInit): Promise<Response>;
  json<T>(path: string, init?: RequestInit): Promise<T>;
  post<T>(path: string, body: unknown, method?: string): Promise<T>;
};

async function readJson(response: Response): Promise<{ error?: string } & Record<string, unknown>> {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text) as { error?: string };
  } catch {
    return { error: text };
  }
}

export function createApi(baseUrl: string, getToken: TokenGetter): Api {
  const root = baseUrl.replace(/\/+$/, "");

  async function request(path: string, init: RequestInit = {}): Promise<Response> {
    const headers = new Headers(init.headers);
    let token: string | null = null;
    try {
      token = await getToken();
    } catch {
      token = null;
    }
    if (token) headers.set("Authorization", `Bearer ${token}`);
    try {
      return await fetch(`${root}${path}`, { ...init, headers });
    } catch {
      throw new Error("Could not reach Sawt. Check the server address in Settings.");
    }
  }

  async function json<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await request(path, init);
    const contentType = response.headers.get("Content-Type") || "";
    if (contentType.includes("audio")) {
      if (!response.ok) {
        const payload = await readJson(response).catch(() => ({ error: "" }));
        throw new Error(payload.error || "request failed");
      }
      return response as unknown as T;
    }
    const payload = await readJson(response);
    if (!response.ok) throw new Error(payload.error || "request failed");
    return payload as T;
  }

  async function post<T>(path: string, body: unknown, method = "POST"): Promise<T> {
    return json<T>(path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  return { request, json, post };
}

export async function fetchConfig(baseUrl: string): Promise<ServerConfig> {
  const root = baseUrl.replace(/\/+$/, "");
  let response: Response;
  try {
    response = await fetch(`${root}/api/config`);
  } catch {
    throw new Error("Could not reach that server. Check the address and try again.");
  }
  const payload = (await response.json().catch(() => ({}))) as ServerConfig & { error?: string };
  if (!response.ok) throw new Error(payload.error || "Could not read the server.");
  return payload;
}

export function loadItems(api: Api, query = ""): Promise<NotebookItem[]> {
  const path = query.trim() ? `/api/items?q=${encodeURIComponent(query.trim())}` : "/api/items";
  return api.json<NotebookItem[]>(path);
}

export function loadSettings(api: Api): Promise<{ language: string }> {
  return api.json("/api/settings");
}

export function saveSettings(api: Api, language: string): Promise<{ language: string }> {
  return api.post("/api/settings", { language });
}

export function previewLesson(api: Api, text: string): Promise<PreviewItem[]> {
  return api.post("/api/preview", { text });
}

export function saveLesson(
  api: Api,
  learnedOn: string,
  text: string,
): Promise<{ skipped?: { spelling: string }[] }> {
  return api.post("/api/lessons", { learned_on: learnedOn, text });
}

export function importCsv(
  api: Api,
  csv: string,
  learnedOn: string,
  language: string,
): Promise<{ days: number; items: number }> {
  return api.post("/api/import-csv", { csv, learned_on: learnedOn, language });
}

export function updateItem(api: Api, id: number, spelling: string, gloss: string): Promise<NotebookItem> {
  return api.post(`/api/items/${id}`, { spelling, gloss }, "PUT");
}

export function similarItems(api: Api, id: number): Promise<{ spelling: string; gloss: string }[]> {
  return api.json(`/api/items/${id}/similar`);
}

export function judgeSentence(api: Api, itemId: number, sentence: string, language: string): Promise<Judgment> {
  return api.post("/api/practice", { item_id: itemId, sentence, language });
}

export function loadNextLesson(api: Api): Promise<NextLesson> {
  return api.json("/api/next-lesson");
}

export function saveCalendar(api: Api, url: string): Promise<{ connected: boolean }> {
  return api.post("/api/calendar", { url });
}

async function readNdjson(response: Response, onObject: (value: unknown, index: number) => Promise<void> | void) {
  const reader = response.body?.getReader?.();
  if (!reader) {
    const text = await response.text();
    const lines = text.split("\n").map((line) => line.trim()).filter(Boolean);
    for (let index = 0; index < lines.length; index += 1) {
      await onObject(JSON.parse(lines[index]) as unknown, index);
    }
    return;
  }
  const decoder = new TextDecoder();
  let buffer = "";
  let index = 0;
  const take = async (chunk: string, flush: boolean) => {
    buffer += chunk;
    let cut = buffer.indexOf("\n");
    while (cut >= 0) {
      const line = buffer.slice(0, cut).trim();
      buffer = buffer.slice(cut + 1);
      if (line) {
        await onObject(JSON.parse(line) as unknown, index);
        index += 1;
      }
      cut = buffer.indexOf("\n");
    }
    if (flush && buffer.trim()) {
      await onObject(JSON.parse(buffer.trim()) as unknown, index);
    }
  };
  while (true) {
    const { value, done } = await reader.read();
    if (value) await take(decoder.decode(value, { stream: !done }), false);
    if (done) {
      await take(decoder.decode(), true);
      break;
    }
  }
}

export async function postTalk(
  api: Api,
  body: Record<string, unknown>,
  onReply: (reply: TalkReply) => void,
  playWav: (bytes: Uint8Array) => Promise<void>,
  speakMissing: string,
): Promise<void> {
  const response = await api.request("/api/talk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, speak: true }),
  });
  const contentType = response.headers.get("Content-Type") || "";
  if (!response.ok) {
    const payload = await readJson(response);
    throw new Error(payload.error || "request failed");
  }

  const playReply = async (reply: TalkReply, audio?: { audio_wav_base64?: string; error?: string }) => {
    if (audio?.audio_wav_base64) {
      await playWav(decodeBase64(audio.audio_wav_base64));
      return;
    }
    if (reply.arabic) {
      await playSpeak(api, reply.arabic, String(body.language || ""), playWav);
      return;
    }
    throw new Error(audio?.error || speakMissing);
  };

  if (!contentType.includes("ndjson")) {
    const reply = (await readJson(response)) as TalkReply;
    onReply(reply);
    await playReply(reply);
    return;
  }

  let reply: TalkReply | null = null;
  let heard = false;
  await readNdjson(response, async (value, index) => {
    if (index === 0) {
      reply = value as TalkReply;
      onReply(reply);
      return;
    }
    const audio = value as { audio_wav_base64?: string; error?: string };
    if (audio.error && !audio.audio_wav_base64) throw new Error(audio.error || speakMissing);
    if (!audio.audio_wav_base64) throw new Error(speakMissing);
    await playWav(decodeBase64(audio.audio_wav_base64));
    heard = true;
  });
  if (!reply) throw new Error("request failed");
  if (!heard) await playReply(reply);
}

async function playSpeak(
  api: Api,
  text: string,
  language: string,
  playWav: (bytes: Uint8Array) => Promise<void>,
) {
  const response = await api.request("/api/speak", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, language }),
  });
  if (!response.ok) {
    const payload = await readJson(response).catch(() => ({ error: "" }));
    throw new Error(payload.error || "Could not play speech.");
  }
  await playWav(new Uint8Array(await response.arrayBuffer()));
}
