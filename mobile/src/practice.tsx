import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { judgeSentence, postTalk, similarItems } from "./api";
import { UI, copy } from "./copy";
import {
  assertReplyMatchesLearning,
  correctionNote,
  hasSpeechScript,
  micLocale,
  randomId,
} from "./logic";
import { playWavBytes, stopPlayback } from "./playback";
import { useSession } from "./session";
import { getSpeechModule, stopSpeech, type SpeechErrorEvent, type SpeechResultEvent, type SpeechVolumeEvent } from "./speech";
import type { LearningLanguage, NotebookItem, TalkReply, TalkTurn, VisibleTurn } from "./types";

type VoicePhase = "idle" | "listening" | "speaking";

type PracticeValue = {
  phase: VoicePhase;
  scene: string;
  line: string;
  gloss: string;
  error: string;
  log: VisibleTurn[];
  volume: number;
  speechReady: boolean;
  activeWord: NotebookItem | null;
  similar: { spelling: string; gloss: string }[];
  sentence: string;
  setSentence: (value: string) => void;
  judgment: { text: string; tone: "ok" | "warn" | "" };
  judging: boolean;
  toggleOrb: () => void;
  chooseScene: (scene: string) => void;
  sendTyped: (text: string) => void;
  openWord: (item: NotebookItem) => void;
  patchWord: (id: number, spelling: string, gloss: string) => void;
  checkSentence: () => Promise<void>;
};

const PracticeContext = createContext<PracticeValue | null>(null);

export function PracticeProvider({ children }: { children: ReactNode }) {
  const { api, language } = useSession();
  const languageRef = useRef<LearningLanguage>(language);
  languageRef.current = language;
  const apiRef = useRef(api);
  apiRef.current = api;

  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [scene, setScene] = useState("");
  const [line, setLine] = useState("");
  const [gloss, setGloss] = useState("");
  const [error, setError] = useState("");
  const [log, setLog] = useState<VisibleTurn[]>([]);
  const [volume, setVolume] = useState(0);
  const [speechReady, setSpeechReady] = useState(false);
  const [activeWord, setActiveWord] = useState<NotebookItem | null>(null);
  const [similar, setSimilar] = useState<{ spelling: string; gloss: string }[]>([]);
  const [sentence, setSentence] = useState("");
  const [judgment, setJudgment] = useState<{ text: string; tone: "ok" | "warn" | "" }>({ text: "", tone: "" });
  const [judging, setJudging] = useState(false);

  const conversing = useRef(false);
  const sceneRef = useRef("");
  sceneRef.current = scene;
  const talkLog = useRef<TalkTurn[]>([]);
  const pending = useRef("");
  const draft = useRef("");
  const pauseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const listening = useRef(false);
  const generation = useRef(0);

  const clearTimer = () => {
    if (pauseTimer.current) clearTimeout(pauseTimer.current);
    pauseTimer.current = null;
  };

  const showLine = (nextLine: string, nextGloss: string) => {
    setLine(nextLine);
    setGloss(nextGloss);
  };

  const appendTurn = useCallback((who: string, spoken: string, meaning?: string, note?: string) => {
    setLog((current) => [
      ...current,
      { id: randomId(), who, line: spoken, gloss: meaning || undefined, note: note || undefined },
    ]);
  }, []);

  const clearHistory = useCallback(() => {
    talkLog.current = [];
    pending.current = "";
    draft.current = "";
    clearTimer();
    setLog([]);
    showLine("", "");
    setError("");
  }, []);

  const halt = useCallback(() => {
    listening.current = false;
    clearTimer();
    pending.current = "";
    draft.current = "";
    stopSpeech();
    stopPlayback();
  }, []);

  const resetCall = useCallback(() => {
    generation.current += 1;
    conversing.current = false;
    halt();
    clearHistory();
    setScene("");
    sceneRef.current = "";
    setPhase("idle");
    setVolume(0);
  }, [clearHistory, halt]);

  useEffect(() => {
    setSpeechReady(getSpeechModule() !== null);
    resetCall();
  }, [language, resetCall]);

  const startListening = useCallback(async () => {
    const mod = getSpeechModule();
    if (!mod) {
      conversing.current = false;
      setPhase("idle");
      setError(UI.noSpeech);
      return;
    }
    if (listening.current) return;
    const permission = await mod.requestPermissionsAsync();
    if (!permission.granted) {
      conversing.current = false;
      setPhase("idle");
      setError(UI.micDenied);
      return;
    }
    setError("");
    setPhase("listening");
    listening.current = true;
    try {
      mod.start({
        lang: micLocale(languageRef.current),
        interimResults: true,
        continuous: true,
        maxAlternatives: 1,
        addsPunctuation: false,
        iosVoiceProcessingEnabled: true,
        volumeChangeEventOptions: { enabled: true, intervalMillis: 80 },
      });
    } catch {
      listening.current = false;
      conversing.current = false;
      setPhase("idle");
      setError(UI.noSpeech);
    }
  }, []);

  const sendTalk = useCallback(
    async (text: string, options?: { opener?: boolean }) => {
      const said = text.trim();
      if (!said || !conversing.current) return;
      const token = generation.current;
      const learning = languageRef.current;
      if (!options?.opener) talkLog.current.push({ role: "user", text: said });
      setPhase("speaking");
      setError("");
      try {
        await postTalk(
          apiRef.current,
          {
            turns: options?.opener ? [{ role: "user", text: said }] : talkLog.current.slice(-6),
            scene: sceneRef.current,
            language: learning,
            ...(options?.opener ? { start: false } : {}),
          },
          (reply) => {
            if (!conversing.current || token !== generation.current) return;
            assertReplyMatchesLearning(learning, reply);
            paintReply(learning, said, reply, Boolean(options?.opener));
          },
          playWavBytes,
          copy(learning, "speakMissing"),
        );
      } catch (err) {
        if (token !== generation.current) return;
        setError(err instanceof Error ? err.message : "request failed");
        if (options?.opener) {
          conversing.current = false;
          setPhase("idle");
          return;
        }
        talkLog.current.pop();
        if (!conversing.current) {
          setPhase("idle");
          return;
        }
      }
      if (!conversing.current || token !== generation.current) {
        setPhase("idle");
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 300));
      if (conversing.current && token === generation.current) await startListening();
      else setPhase("idle");
    },
    [appendTurn, startListening],
  );

  const paintReply = (learning: LearningLanguage, said: string, reply: TalkReply, opener: boolean) => {
    if (!opener) {
      const spokeNative = learning === "japanese" && /[\u3040-\u30ff\u3400-\u9fff]/.test(said);
      const last = talkLog.current[talkLog.current.length - 1];
      if (last?.role === "user") last.text = spokeNative ? said : reply.you_arabizi || said;
      if (spokeNative) appendTurn(UI.you, said, reply.you_arabizi || reply.you_english);
      else appendTurn(UI.you, reply.you_arabizi || said, reply.you_english);
    }
    const note = opener ? "" : correctionNote(learning, said, reply, UI.tryPrefix);
    appendTurn(UI.sawt, reply.arabizi || "", reply.english, note);
    showLine(reply.arabizi || "", reply.english || "");
    if (reply.arabizi) talkLog.current.push({ role: "assistant", text: reply.arabizi });
    if (reply.arabic && !hasSpeechScript(learning, reply.arabic) && !reply.arabizi) {
      throw new Error(copy(learning, "speakMissing"));
    }
  };

  const sendTalkRef = useRef(sendTalk);
  sendTalkRef.current = sendTalk;

  const waitForPause = useCallback((milliseconds: number) => {
    clearTimer();
    pauseTimer.current = setTimeout(() => {
      const said = `${pending.current}${draft.current}`.trim();
      pending.current = "";
      draft.current = "";
      if (!said || !conversing.current) return;
      listening.current = false;
      stopSpeech();
      void sendTalkRef.current(said);
    }, milliseconds);
  }, []);

  useEffect(() => {
    const mod = getSpeechModule();
    if (!mod) return;
    const resultSub = mod.addListener("result", ((event: SpeechResultEvent) => {
      const piece = event.results[0]?.transcript ?? "";
      if (!piece.trim() && !event.isFinal) return;
      if (event.isFinal) {
        pending.current += piece;
        if (pending.current && !pending.current.endsWith(" ")) pending.current += " ";
        draft.current = "";
      } else {
        draft.current = piece;
      }
      const live = `${pending.current}${draft.current}`.trim();
      if (live) {
        showLine(live, "");
        waitForPause(!draft.current.trim() && event.isFinal ? 700 : 1100);
      }
    }) as (event: never) => void);
    const errorSub = mod.addListener("error", ((event: SpeechErrorEvent) => {
      if (event.error === "not-allowed") {
        conversing.current = false;
        listening.current = false;
        setPhase("idle");
        setError(UI.micDenied);
        return;
      }
      if (event.error === "aborted" || event.error === "no-speech") return;
      if (event.error === "audio-capture" || event.error === "service-not-allowed") {
        setError(UI.noSpeech);
      }
    }) as (event: never) => void);
    const endSub = mod.addListener("end", (() => {
      if (!listening.current) return;
      listening.current = false;
      if (conversing.current) {
        setTimeout(() => {
          if (conversing.current && !listening.current) void startListening();
        }, 250);
      }
    }) as (event: never) => void);
    const volumeSub = mod.addListener("volumechange", ((event: SpeechVolumeEvent) => {
      const level = Math.max(0, Math.min(1, event.value / 8));
      setVolume(level);
    }) as (event: never) => void);
    return () => {
      resultSub.remove();
      errorSub.remove();
      endSub.remove();
      volumeSub.remove();
    };
  }, [startListening, waitForPause]);

  const openVoice = useCallback(
    (nextScene?: string) => {
      if (nextScene !== undefined) {
        if (conversing.current) halt();
        conversing.current = false;
        clearHistory();
        setScene(nextScene);
        sceneRef.current = nextScene;
      } else if (!conversing.current) {
        clearHistory();
      }
      showLine("", "");
      setPhase("listening");
      conversing.current = true;
      if (sceneRef.current) {
        setPhase("speaking");
        void sendTalkRef.current(UI.startScene, { opener: true });
        return;
      }
      void startListening();
    },
    [clearHistory, halt, startListening],
  );

  const toggleOrb = useCallback(() => {
    if (conversing.current) {
      resetCall();
      return;
    }
    openVoice();
  }, [openVoice, resetCall]);

  const chooseScene = useCallback(
    (next: string) => {
      openVoice(next);
    },
    [openVoice],
  );

  const sendTyped = useCallback((text: string) => {
    const said = text.trim();
    if (!said) return;
    if (!conversing.current) {
      clearHistory();
      conversing.current = true;
    } else {
      listening.current = false;
      clearTimer();
      stopSpeech();
    }
    void sendTalkRef.current(said);
  }, [clearHistory]);

  const patchWord = useCallback((id: number, nextSpelling: string, nextGloss: string) => {
    setActiveWord((current) =>
      current && current.id === id ? { ...current, spelling: nextSpelling, gloss: nextGloss } : current,
    );
  }, []);

  const openWord = useCallback(
    (item: NotebookItem) => {
      setActiveWord(item);
      setSentence("");
      setJudgment({ text: "", tone: "" });
      setSimilar([]);
      similarItems(api, item.id)
        .then((matches) => {
          if (Array.isArray(matches)) setSimilar(matches);
        })
        .catch(() => setSimilar([]));
    },
    [api],
  );

  const checkSentence = useCallback(async () => {
    if (!activeWord) return;
    setJudgment({ text: "", tone: "" });
    setJudging(true);
    try {
      const result = await judgeSentence(api, activeWord.id, sentence, language);
      const used = result.uses_target ? UI.usesTarget : UI.missesTarget;
      const fit = result.fits_meaning ? UI.fitsMeaning : UI.missesMeaning;
      setJudgment({
        text: `${used}; ${fit}. ${result.comment}`,
        tone: result.uses_target && result.fits_meaning ? "ok" : "warn",
      });
    } catch (err) {
      setJudgment({ text: err instanceof Error ? err.message : "request failed", tone: "warn" });
    } finally {
      setJudging(false);
    }
  }, [activeWord, api, language, sentence]);

  const value = useMemo<PracticeValue>(
    () => ({
      phase,
      scene,
      line,
      gloss,
      error,
      log,
      volume,
      speechReady,
      activeWord,
      similar,
      sentence,
      setSentence,
      judgment,
      judging,
      toggleOrb,
      chooseScene,
      sendTyped,
      openWord,
      patchWord,
      checkSentence,
    }),
    [
      phase,
      scene,
      line,
      gloss,
      error,
      log,
      volume,
      speechReady,
      activeWord,
      similar,
      sentence,
      judgment,
      judging,
      toggleOrb,
      chooseScene,
      sendTyped,
      openWord,
      patchWord,
      checkSentence,
    ],
  );

  return <PracticeContext.Provider value={value}>{children}</PracticeContext.Provider>;
}

export function usePractice(): PracticeValue {
  const value = useContext(PracticeContext);
  if (!value) throw new Error("Practice is missing");
  return value;
}
