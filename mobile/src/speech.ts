import Constants from "expo-constants";

export type SpeechResultEvent = {
  isFinal: boolean;
  results: { transcript: string }[];
};

export type SpeechErrorEvent = {
  error: string;
  message?: string;
};

export type SpeechVolumeEvent = {
  value: number;
};

type Subscription = { remove: () => void };

export type SpeechModule = {
  start: (options: Record<string, unknown>) => void;
  abort: () => void;
  stop: () => void;
  requestPermissionsAsync: () => Promise<{ granted: boolean }>;
  isRecognitionAvailable?: () => boolean;
  addListener: (event: string, listener: (event: never) => void) => Subscription;
};

let checked = false;
let cached: SpeechModule | null = null;

export function speechRecognitionAvailable(): boolean {
  return getSpeechModule() !== null;
}

export function getSpeechModule(): SpeechModule | null {
  if (checked) return cached;
  checked = true;
  if (Constants.executionEnvironment === "storeClient") {
    cached = null;
    return null;
  }
  try {
    const loaded = require("expo-speech-recognition") as {
      ExpoSpeechRecognitionModule?: SpeechModule;
    };
    const mod = loaded.ExpoSpeechRecognitionModule;
    if (!mod || typeof mod.start !== "function") {
      cached = null;
      return null;
    }
    if (typeof mod.isRecognitionAvailable === "function" && !mod.isRecognitionAvailable()) {
      cached = null;
      return null;
    }
    cached = mod;
  } catch {
    cached = null;
  }
  return cached;
}

export function stopSpeech(): void {
  const mod = getSpeechModule();
  if (!mod) return;
  try {
    mod.abort();
  } catch {
    try {
      mod.stop();
    } catch {
      // The recognizer was already stopped.
    }
  }
}
