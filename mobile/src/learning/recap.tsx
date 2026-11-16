import { useState } from "react";
import { Text } from "react-native";
import * as Crypto from "expo-crypto";
import { Button, ErrorText, Field } from "@/src/components/ui";
import Hint from "./hint";
import { useSession } from "@/src/session";
import { useTheme } from "@/src/theme";
import type { LearningRule } from "@/src/learning";
import Title from "./title";

export default function Recap({
  rule,
  onSaved,
}: {
  rule: LearningRule;
  onSaved: () => void;
}) {
  const theme = useTheme(),
    { api } = useSession();
  const [response, setResponse] = useState(""),
    [reveal, setReveal] = useState(false),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <>
      <Title>{rule.title}</Title>
      <Hint>
        Explain the pattern or write a fresh example before looking at your
        notes.
      </Hint>
      <Field
        label="What can you remember?"
        value={response}
        onChangeText={setResponse}
        multiline
      />
      {!reveal ? (
        <Button label="Reveal my notes" onPress={() => setReveal(true)} />
      ) : (
        <>
          <Text style={{ color: theme.label, lineHeight: 24 }}>
            {rule.explanation}
          </Text>
          {rule.example ? (
            <Text style={{ color: theme.label }}>{rule.example}</Text>
          ) : null}
          <Hint>{rule.source}</Hint>
          {[
            { rating: "again", label: "Need another look · tomorrow" },
            { rating: "partly", label: "Partly recalled · 3 days" },
            { rating: "recalled", label: "Recalled · 7 days" },
          ].map((r) => (
            <Button
              key={r.rating}
              label={r.label}
              disabled={busy}
              kind="secondary"
              onPress={() => {
                setBusy(true);
                api
                  .post("/api/lessons", {
                    action: "recall",
                    request_id: Crypto.randomUUID(),
                    rule_id: rule.id,
                    response,
                    rating: r.rating,
                  })
                  .then(onSaved)
                  .catch((err: unknown) =>
                    setError(
                      err instanceof Error ? err.message : "Could not save",
                    ),
                  )
                  .finally(() => setBusy(false));
              }}
            />
          ))}
        </>
      )}
      <ErrorText>{error}</ErrorText>
    </>
  );
}
