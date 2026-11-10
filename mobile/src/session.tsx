import AsyncStorage from "@react-native-async-storage/async-storage";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { createApi, loadSettings, saveSettings, type Api, type TokenGetter } from "./api";
import { cleanServerUrl, normalizeLearningLanguage } from "./logic";
import type { LearningLanguage } from "./types";

const LANGUAGE_KEY = "sawt.language";

type SessionValue = {
  api: Api;
  apiUrl: string;
  language: LearningLanguage;
  setLanguage: (language: LearningLanguage) => Promise<void>;
  revision: number;
  touchLibrary: () => void;
  authRequired: boolean;
  accountEmail: string;
  replaceServer: (url: string) => Promise<void>;
};

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({
  apiUrl,
  getToken,
  authRequired,
  accountEmail,
  authReady,
  signedIn,
  replaceServer,
  children,
}: {
  apiUrl: string;
  getToken: TokenGetter;
  authRequired: boolean;
  accountEmail: string;
  authReady: boolean;
  signedIn: boolean;
  replaceServer: (url: string) => Promise<void>;
  children: ReactNode;
}) {
  const api = useMemo(() => createApi(apiUrl, getToken), [apiUrl, getToken]);
  const [language, setLanguageState] = useState<LearningLanguage>("arabic");
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let cancelled = false;
    AsyncStorage.getItem(LANGUAGE_KEY).then((stored) => {
      if (!cancelled && stored) setLanguageState(normalizeLearningLanguage(stored));
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!authReady || (authRequired && !signedIn)) return;
    let cancelled = false;
    loadSettings(api)
      .then((payload) => {
        if (cancelled) return;
        const next = normalizeLearningLanguage(payload.language);
        setLanguageState(next);
        void AsyncStorage.setItem(LANGUAGE_KEY, next);
      })
      .catch(() => {
        // Keep the language saved on this phone if the server is briefly unreachable.
      });
    return () => {
      cancelled = true;
    };
  }, [api, authReady, authRequired, signedIn]);

  const setLanguage = useCallback(
    async (next: LearningLanguage) => {
      const previous = language;
      setLanguageState(next);
      await AsyncStorage.setItem(LANGUAGE_KEY, next);
      try {
        const saved = await saveSettings(api, next);
        const confirmed = normalizeLearningLanguage(saved.language || next);
        setLanguageState(confirmed);
        await AsyncStorage.setItem(LANGUAGE_KEY, confirmed);
      } catch (error) {
        setLanguageState(previous);
        await AsyncStorage.setItem(LANGUAGE_KEY, previous);
        throw error;
      }
    },
    [api, language],
  );

  const value = useMemo<SessionValue>(
    () => ({
      api,
      apiUrl,
      language,
      setLanguage,
      revision,
      touchLibrary: () => setRevision((current) => current + 1),
      authRequired,
      accountEmail,
      replaceServer: async (url: string) => replaceServer(cleanServerUrl(url)),
    }),
    [api, apiUrl, language, setLanguage, revision, authRequired, accountEmail, replaceServer],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("Session is missing");
  return value;
}
