import { useState } from "react";
import { Text, View } from "react-native";
import * as Crypto from "expo-crypto";
import { Button, ErrorText, Field } from "@/src/components/ui";
import Hint from "./hint";
import { useSession } from "@/src/session";
import { useTheme } from "@/src/theme";
import type { LearningTask } from "@/src/learning";
import Title from "./title";
import Correction from "./correction";

export default function Workshop({
  task,
  onRefresh,
  onDictionary,
  onBack,
}: {
  task: LearningTask;
  onRefresh: () => Promise<void>;
  onDictionary: () => void;
  onBack: () => void;
}) {
  const { api } = useSession();
  const theme = useTheme();
  const [answer, setAnswer] = useState(task.draft),
    [revision, setRevision] = useState(task.revision),
    [status, setStatus] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const save = (action: "draft" | "attempt") => {
    setBusy(true);
    setError("");
    api
      .post<{ revision: number }>("/api/lessons", {
        action,
        request_id: Crypto.randomUUID(),
        task_id: task.id,
        revision,
        text: answer,
      })
      .then(async (r) => {
        setRevision(r.revision);
        setStatus(action === "draft" ? "Draft saved" : "Attempt saved");
        if (action === "attempt") await onRefresh();
      })
      .catch((err: unknown) =>
        setError(
          err instanceof Error
            ? err.message
            : "Could not save; your text is still here.",
        ),
      )
      .finally(() => setBusy(false));
  };
  return (
    <>
      <Button
        label="Save draft and return to notebook"
        kind="text"
        disabled={busy}
        onPress={() => {
          setBusy(true);
          api
            .post<{ revision: number }>("/api/lessons", {
              action: "draft",
              request_id: Crypto.randomUUID(),
              task_id: task.id,
              revision,
              text: answer,
            })
            .then(onBack)
            .catch((err: unknown) =>
              setError(
                err instanceof Error
                  ? err.message
                  : "Could not save. Your text is still here.",
              ),
            )
            .finally(() => setBusy(false));
        }}
      />
      <Title>Sentence workshop</Title>
      <Text style={{ color: theme.label, lineHeight: 23 }}>{task.prompt}</Text>
      <Hint>
        {task.sentence_count} original sentences
        {task.due_on ? " · due " + task.due_on : ""}
      </Hint>
      <Title>Required words</Title>
      {task.words.map((w) => (
        <Hint key={w.id}>
          {w.spelling} · {w.gloss}
        </Hint>
      ))}
      {task.rules.map((r) => (
        <View key={r.id} style={{ gap: 6 }}>
          <Text style={{ color: theme.label, fontWeight: "600" }}>
            {r.title}
          </Text>
          <Hint>{r.explanation}</Hint>
        </View>
      ))}
      <Field
        label="Your own sentences"
        value={answer}
        onChangeText={(text) => {
          setAnswer(text);
          setStatus("Unsaved changes");
        }}
        multiline
        style={{ minHeight: 200, textAlignVertical: "top" }}
      />
      <Hint>{status}</Hint>
      <ErrorText>{error}</ErrorText>
      <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap" }}>
        <Button
          label="Save draft"
          disabled={busy}
          kind="secondary"
          onPress={() => save("draft")}
        />
        <Button
          label="Save attempt"
          disabled={busy}
          onPress={() => save("attempt")}
        />
      </View>
      <Button
        label="Save draft and look up a word"
        disabled={busy}
        kind="text"
        onPress={() => {
          setBusy(true);
          api
            .post<{ revision: number }>("/api/lessons", {
              action: "draft",
              request_id: Crypto.randomUUID(),
              task_id: task.id,
              revision,
              text: answer,
            })
            .then((r) => {
              setRevision(r.revision);
              onDictionary();
            })
            .catch((err: unknown) =>
              setError(err instanceof Error ? err.message : "Could not save"),
            )
            .finally(() => setBusy(false));
        }}
      />
      <Button
        label={
          task.status === "done" ? "Reopen homework" : "Mark homework ready"
        }
        disabled={busy}
        kind="secondary"
        onPress={() => {
          setBusy(true);
          api
            .post("/api/lessons", {
              action: "task-status",
              request_id: Crypto.randomUUID(),
              task_id: task.id,
              status: task.status === "done" ? "open" : "done",
            })
            .then(onRefresh)
            .catch((err: unknown) =>
              setError(err instanceof Error ? err.message : "Could not update"),
            )
            .finally(() => setBusy(false));
        }}
      />
      <Title>Attempts and corrections</Title>
      {!task.attempts?.length ? (
        <Hint>
          Your original attempts will stay here when you add a correction.
        </Hint>
      ) : null}
      {task.attempts?.map((a) => (
        <View
          key={a.id}
          style={{
            gap: 10,
            paddingVertical: 14,
            borderBottomWidth: 1,
            borderBottomColor: theme.separator,
          }}
        >
          <Hint>{new Date(a.created_at).toLocaleString()}</Hint>
          <Text style={{ color: theme.label, lineHeight: 24 }}>{a.text}</Text>
          {a.corrections.map((c) => (
            <View
              key={c.id}
              style={{
                borderLeftColor: theme.blue,
                borderLeftWidth: 2,
                paddingLeft: 12,
              }}
            >
              <Hint>{c.author}</Hint>
              <Text style={{ color: theme.label }}>{c.text}</Text>
              <Hint>{c.note}</Hint>
            </View>
          ))}
          <Correction attemptId={a.id} onSaved={onRefresh} />
        </View>
      ))}
    </>
  );
}
