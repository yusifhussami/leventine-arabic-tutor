import type { LearningLanguage } from "./types";

export const UI = {
  tabToday: "Today",
  tabPractice: "Practice",
  tabWords: "Words",
  tabChecklist: "Checklist",
  tabSettings: "Settings",
  checklistHint:
    "Light goals for this language. Tap the chevron for a note. Tick to move into Done — untick to bring it back.",
  checklistNew: "New item",
  checklistEmpty: "No items yet.",
  checklistDone: "Done",
  checklistNote: "Description",
  checklistDelete: "Delete",
  addLesson: "Add a lesson",
  lessonDate: "Date",
  wordsLabel: "Words",
  importCsv: "Import a CSV",
  importHint:
    "Starting empty? Upload a sheet with Word and Meaning columns. Date Added groups them by lesson day.",
  chooseCsv: "Choose CSV",
  importWords: "Import words",
  noCsvChosen: "No file chosen",
  emptyLibrary: "No lessons saved yet.",
  emptyLibraryHint: "Paste a lesson on Today, or import a CSV there.",
  preview: "Preview",
  saveLesson: "Save lesson",
  nextLesson: "Next lesson",
  lookingUpLesson: "Looking up your next Arabic lesson.",
  account: "Account",
  accountHint: "Sign in to keep your words on your account.",
  accountLocal: "This local notebook does not need a sign-in.",
  signedIn: "Signed in",
  signIn: "Sign in",
  signOut: "Sign out",
  manageAccount: "Manage account",
  language: "Language you're learning",
  calendar: "Calendar",
  calendarHint: "Paste the secret iCal address from Google Calendar.",
  icalLink: "iCal link",
  saveCalendar: "Save calendar",
  tapToTalk: "Tap to talk",
  listening: "Listening",
  speaking: "Speaking",
  sceneCoffee: "Coffee",
  sceneRestaurant: "Restaurant",
  sceneShop: "Shop",
  sceneTaxi: "Taxi",
  chooseWord: "Choose a saved word, then write one sentence that uses it.",
  writeWith: "Write with",
  yourSentence: "Your sentence",
  checkSentence: "Check sentence",
  search: "Search",
  searchResults: "Best matches",
  noSearchMatches: "No words match that search.",
  connectCalendar: "Connect Google Calendar to see your next Arabic lesson.",
  noLesson: "No upcoming Preply lesson on that calendar.",
  calendarReadError: "Could not read the calendar.",
  edit: "Edit",
  save: "Save",
  cancel: "Cancel",
  usesTarget: "uses the target",
  missesTarget: "does not use the target",
  fitsMeaning: "fits the meaning",
  missesMeaning: "does not fit the meaning",
  tryPrefix: "Try: ",
  you: "You",
  sawt: "Sawt",
  noSpeech: "Speech recognition isn't available in this build. Type a line instead.",
  micDenied: "Allow the microphone, then tap the circle.",
  speakFailed: "Could not play speech.",
  startScene: "Start. You speak first, in the place, one short line.",
  languageHint:
    "The app stays in English. Pick the language you practice: speaking, listening, and spellings follow that choice.",
  gateBody: "Sign in to keep your words and practice on your own account.",
  recent: "Recent",
  server: "Server",
  serverHint: "The Vercel address for this notebook. Words stay on that account.",
  serverPlaceholder: "https://your-project.vercel.app",
  saveServer: "Save server",
  couldNotSaveLanguage: "Could not save language.",
  searchFailed: "Search failed.",
} as const;

const MODE = {
  arabic: {
    lessonHint: "Each Arabizi spelling stays with its English meaning.",
    pastePlaceholder: "eb7as - to search\n6awaret - I developed\n8ararat = decisions",
    colArabizi: "Arabizi",
    colGloss: "English",
    typeArabizi: "Or type in Arabizi",
    sentencePlaceholder: "Arabizi that uses this word",
    speakMissing: "No Arabic script to speak. Type a line, or try again.",
    importHint: UI.importHint,
  },
  japanese: {
    lessonHint: "Each kana (or romaji) spelling stays with its English meaning.",
    pastePlaceholder: "hello - こんにちは\nthank you - ありがとう\nwater = みず",
    colArabizi: "Kana",
    colGloss: "English",
    typeArabizi: "Or type in Japanese or romaji",
    sentencePlaceholder: "Japanese that uses this word",
    speakMissing: "No Japanese script to speak. Type a line, or try again.",
    importHint:
      "Japanese sheet: Kanji, Kana (hiragana/katakana), and Meaning/English. Practice uses kana; kanji stays on the meaning line.",
  },
} as const;

export function copy(language: LearningLanguage, key: keyof typeof UI | keyof (typeof MODE)["arabic"]): string {
  const mode = MODE[language] as Record<string, string>;
  if (key in mode) return mode[key];
  return UI[key as keyof typeof UI];
}

export function wordCount(n: number): string {
  return n === 1 ? "1 word" : `${n} words`;
}

export function importDone(days: number, items: number): string {
  if (items === 1) return "Imported 1 word.";
  const dayLabel = days === 1 ? "lesson day." : "lesson days.";
  return `Imported ${items} words across ${days} ${dayLabel}`;
}

export function brandMark(language: LearningLanguage): string {
  return language === "japanese" ? "音" : "صوت";
}
