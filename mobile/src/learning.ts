export type LearningWord = {
  id: number;
  spelling: string;
  gloss: string;
  arabic_script?: string;
};
export type LearningRule = {
  id: number;
  title: string;
  explanation: string;
  example: string;
  source: string;
  due_on: string;
  session_id?: number;
};
export type LearningTask = {
  id: number;
  session_id?: number;
  prompt: string;
  words: LearningWord[];
  rules: LearningRule[];
  sentence_count: number;
  due_on: string;
  status: "open" | "done";
  draft: string;
  revision: number;
  attempts?: LearningAttempt[];
};
export type LearningAttempt = {
  id: number;
  text: string;
  created_at: string;
  corrections: { id: number; text: string; note: string; author: string }[];
};
export type LearningSession = {
  id: number;
  title: string;
  teacher: string;
  learned_on: string;
  goal: string;
  words: LearningWord[];
};
export type RuleSeed = {
  id: string;
  title: string;
  explanation: string;
  prompt: string;
  source: string;
};
export type LearningWorkspace = {
  teacher: string;
  sessions: LearningSession[];
  tasks: LearningTask[];
  rules: LearningRule[];
  due_rules: LearningRule[];
  guide: RuleSeed[];
};
export type DictionaryEntry = {
  id: number;
  arabic: string;
  meaning: string;
  url: string;
  forms: {
    arabic: string;
    translit?: string;
    conjugation?: string;
    dialect?: string;
  }[];
  notice?: string;
};
export type FormKind =
  | "noun"
  | "verbal_noun"
  | "adjective"
  | "past"
  | "imperfect"
  | "present"
  | "imperative"
  | "continuous"
  | "active_participle"
  | "passive_participle"
  | "other";
export type FamilyForm = {
  kind: FormKind;
  arabic: string;
  arabizi: string;
  subject: string;
  meaning: string;
  example: string;
  source: "teacher" | "dictionary" | "learner" | "suggestion";
  source_url: string;
};
export type WordFamily = {
  item: LearningWord;
  revision: number;
  forms: FamilyForm[];
};
export const FORM_LABELS: { kind: FormKind; label: string }[] = [
  { kind: "noun", label: "Noun" },
  { kind: "verbal_noun", label: "Verbal noun" },
  { kind: "adjective", label: "Adjective" },
  { kind: "past", label: "Past" },
  { kind: "imperfect", label: "Bare imperfect" },
  { kind: "present", label: "b-present" },
  { kind: "imperative", label: "Imperative" },
  { kind: "continuous", label: "Continuous" },
  { kind: "active_participle", label: "Active participle" },
  { kind: "passive_participle", label: "Passive participle" },
  { kind: "other", label: "Other" },
];
