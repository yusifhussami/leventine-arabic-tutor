export type LearningLanguage = "arabic" | "japanese";

export type NotebookItem = {
  id: number;
  spelling: string;
  gloss: string;
  kind: string;
  learned_on: string;
  lesson_id: number;
  language?: string;
};

export type PreviewItem = {
  spelling: string;
  gloss: string;
  kind: string;
};

export type TalkReply = {
  you_arabizi?: string;
  you_english?: string;
  arabic?: string;
  arabizi?: string;
  english?: string;
  correction?: string;
  better?: string;
  language?: string;
};

export type TalkTurn = {
  role: "user" | "assistant";
  text: string;
};

export type VisibleTurn = {
  id: string;
  who: string;
  line: string;
  gloss?: string;
  note?: string;
};

export type Judgment = {
  uses_target: boolean;
  fits_meaning: boolean;
  comment: string;
};

export type ChecklistItem = {
  id: string;
  title: string;
  description: string;
  done: boolean;
  open: boolean;
};

export type ServerConfig = {
  clerkPublishableKey?: string;
  authRequired?: boolean;
};

export type NextLesson = {
  connected: boolean;
  lesson: { start: string; summary?: string } | null;
  error?: string;
};
