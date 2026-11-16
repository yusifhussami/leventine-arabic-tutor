import { useCallback, useEffect, useState } from "react";
import { useLocalSearchParams, useFocusEffect } from "expo-router";
import { Text, View } from "react-native";
import { BodyScroll, Button, ErrorText, Screen } from "@/src/components/ui";
import { useSession } from "@/src/session";
import { useTheme } from "@/src/theme";
import type {
  LearningRule,
  LearningTask,
  LearningWorkspace,
  RuleSeed,
  WordFamily,
} from "@/src/learning";

import Hint from "@/src/learning/hint";
import Title from "@/src/learning/title";
import Capture from "@/src/learning/capture";
import Workshop from "@/src/learning/workshop";
import Recap from "@/src/learning/recap";
import Dictionary from "@/src/learning/dictionary";
import Family from "@/src/learning/family";

type ViewState =
  | { kind: "home" }
  | { kind: "capture"; seed?: RuleSeed }
  | { kind: "task"; task: LearningTask }
  | { kind: "recap"; rule: LearningRule }
  | { kind: "dictionary" }
  | { kind: "family"; family: WordFamily };

export default function LearnScreen() {
  const session = useSession();
  return (
    <LearnNotebook
      key={`${session.language}:${session.accountEmail}:${session.apiUrl}`}
    />
  );
}
function LearnNotebook() {
  const theme = useTheme(),
    { api, language, touchLibrary } = useSession();
  const params = useLocalSearchParams<{ wordId?: string; view?: string }>();
  const [workspace, setWorkspace] = useState<LearningWorkspace | null>(null),
    [view, setView] = useState<ViewState>({ kind: "home" }),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  const refresh = useCallback(async () => {
    const result = await api.json<LearningWorkspace>(
      "/api/lessons?action=workspace",
    );
    setWorkspace(result);
    return result;
  }, [api]);
  useEffect(() => {
    let current = true;
    api
      .json<LearningWorkspace>("/api/lessons?action=workspace")
      .then((data) => {
        if (current) setWorkspace(data);
      })
      .catch((err: unknown) => {
        if (current)
          setError(
            err instanceof Error ? err.message : "Could not load your notebook",
          );
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [api, language]);
  useFocusEffect(
    useCallback(() => {
      let current = true;
      if (params.wordId) {
        api
          .json<WordFamily>(
            "/api/items?action=family&id=" + encodeURIComponent(params.wordId),
          )
          .then((family) => {
            if (current) setView({ kind: "family", family });
          })
          .catch((err: unknown) =>
            setError(
              err instanceof Error ? err.message : "Could not load this word",
            ),
          );
      } else if (params.view === "dictionary") setView({ kind: "dictionary" });
      return () => {
        current = false;
      };
    }, [api, params.wordId, params.view]),
  );
  const task = async (id: number) => {
    setError("");
    try {
      setView({
        kind: "task",
        task: await api.json<LearningTask>("/api/lessons?action=task&id=" + id),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the task");
    }
  };
  const home = () => {
    setView({ kind: "home" });
    refresh().catch((err: unknown) =>
      setError(err instanceof Error ? err.message : "Could not refresh"),
    );
  };
  return (
    <Screen title="Learning notebook">
      <BodyScroll>
        <ErrorText>{error}</ErrorText>
        {view.kind !== "home" && view.kind !== "task" ? (
          <Button label="Back to notebook" kind="text" onPress={home} />
        ) : null}
        {view.kind === "home" ? (
          <>
            <Text
              style={{ fontSize: 28, fontWeight: "600", color: theme.label }}
            >
              From the lesson to your own sentences
            </Text>
            <Hint>
              Keep the words, grammar, homework, and your teacher’s corrections
              together.
            </Hint>
            <Button
              label="Capture a lesson"
              onPress={() => setView({ kind: "capture" })}
            />
            {language === "arabic" ? (
              <Button
                label="Look up a word"
                kind="secondary"
                onPress={() => setView({ kind: "dictionary" })}
              />
            ) : null}
            {loading ? <Hint>Loading your notebook…</Hint> : null}
            {!loading && !workspace ? (
              <Button
                label="Try again"
                onPress={() => {
                  refresh().catch((err: unknown) =>
                    setError(
                      err instanceof Error ? err.message : "Could not load",
                    ),
                  );
                }}
              />
            ) : null}
            {workspace ? (
              <>
                <Title>Sentence homework</Title>
                {!workspace.tasks.some((t) => t.status === "open") ? (
                  <Hint>
                    Capture a lesson to get a writing brief using its words and
                    rules.
                  </Hint>
                ) : null}
                {workspace.tasks
                  .filter((t) => t.status === "open")
                  .map((t) => (
                    <View
                      key={t.id}
                      style={{
                        gap: 8,
                        paddingVertical: 14,
                        borderBottomColor: theme.separator,
                        borderBottomWidth: 1,
                      }}
                    >
                      <Text style={{ color: theme.label }}>{t.prompt}</Text>
                      <Hint>
                        {t.sentence_count} sentences · {t.words.length} words ·{" "}
                        {t.rules.length} rules
                      </Hint>
                      <Button
                        label="Open workshop"
                        kind="tint"
                        onPress={() => {
                          void task(t.id);
                        }}
                      />
                    </View>
                  ))}
                <Title>Recall your rules</Title>
                {!workspace.rules.length ? (
                  <Hint>
                    Save a rule in a lesson. Explain it before revealing your
                    notes when you recap.
                  </Hint>
                ) : null}
                {workspace.rules.slice(0, 12).map((rule) => (
                  <View key={rule.id} style={{ gap: 6, paddingVertical: 8 }}>
                    <Text style={{ color: theme.label, fontWeight: "600" }}>
                      {rule.title}
                    </Text>
                    <Hint>Next recap: {rule.due_on}</Hint>
                    <Button
                      label="Recall it"
                      kind="text"
                      onPress={() => setView({ kind: "recap", rule })}
                    />
                  </View>
                ))}
                <Title>Your lessons</Title>
                {workspace.sessions.map((s) => (
                  <View key={s.id} style={{ gap: 4, paddingVertical: 8 }}>
                    <Text style={{ color: theme.label, fontWeight: "600" }}>
                      {s.title}
                    </Text>
                    <Hint>
                      {s.learned_on}
                      {s.teacher ? " · " + s.teacher : ""} · {s.words.length}{" "}
                      words
                    </Hint>
                    {s.goal ? <Hint>{s.goal}</Hint> : null}
                    <Button
                      label="Open homework and attempts"
                      kind="text"
                      onPress={() => {
                        const savedTask = workspace.tasks.find(
                          (t) => t.session_id === s.id,
                        );
                        if (savedTask) void task(savedTask.id);
                      }}
                    />
                  </View>
                ))}
                {workspace.guide.length ? (
                  <Title>Patterns from the green verbs book</Title>
                ) : null}
                {workspace.guide.map((seed) => (
                  <View key={seed.id} style={{ gap: 6, paddingVertical: 10 }}>
                    <Text style={{ color: theme.label, fontWeight: "600" }}>
                      {seed.title}
                    </Text>
                    <Hint>{seed.explanation}</Hint>
                    <Hint>{seed.source}</Hint>
                    <Button
                      label="Use in a lesson"
                      kind="text"
                      onPress={() => setView({ kind: "capture", seed })}
                    />
                  </View>
                ))}
              </>
            ) : null}
          </>
        ) : null}
        {view.kind === "capture" ? (
          <Capture
            teacher={workspace?.teacher || ""}
            seed={view.seed}
            onSaved={async (id) => {
              await refresh();
              touchLibrary();
              await task(id);
            }}
          />
        ) : null}
        {view.kind === "task" ? (
          <Workshop
            key={view.task.id + ":" + view.task.revision}
            task={view.task}
            onRefresh={() => task(view.task.id)}
            onDictionary={() => setView({ kind: "dictionary" })}
            onBack={home}
          />
        ) : null}
        {view.kind === "recap" ? (
          <Recap key={view.rule.id} rule={view.rule} onSaved={home} />
        ) : null}
        {view.kind === "dictionary" ? (
          <Dictionary onSaved={() => touchLibrary()} />
        ) : null}
        {view.kind === "family" ? <Family initial={view.family} /> : null}
      </BodyScroll>
    </Screen>
  );
}
