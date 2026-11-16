import { useState } from "react";
import { Linking, Text, View } from "react-native";
import { Button, ErrorText, Field } from "@/src/components/ui";
import Hint from "./hint";
import { useSession } from "@/src/session";
import { useTheme } from "@/src/theme";
import type { DictionaryEntry } from "@/src/learning";
import Title from "./title";

export default function Dictionary({ onSaved }: { onSaved: () => void }) {
  const { api } = useSession();
  const theme = useTheme();
  const [query, setQuery] = useState(""),
    [entries, setEntries] = useState<DictionaryEntry[]>([]),
    [status, setStatus] = useState(
      "Search English, Arabic, or available Arabizi spellings.",
    ),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <>
      <Title>Dictionary</Title>
      <Hint>
        Arwords’ cached public index, inside Sawt. Looking up a word does not
        add it to your notebook.
      </Hint>
      <Field
        label="Find a word or meaning"
        value={query}
        onChangeText={setQuery}
        autoCapitalize="none"
      />
      <Button
        label={busy ? "Searching…" : "Search"}
        disabled={busy}
        onPress={() => {
          setBusy(true);
          setError("");
          api
            .json<{ entries: DictionaryEntry[]; total: number }>(
              "/api/items?action=dictionary&q=" + encodeURIComponent(query),
            )
            .then((data) => {
              setEntries(data.entries);
              setStatus(
                data.total
                  ? `${data.total} matches. Choose the meaning you need.`
                  : "No match. Try the English meaning or a shorter spelling.",
              );
            })
            .catch((err: unknown) =>
              setError(err instanceof Error ? err.message : "Could not search"),
            )
            .finally(() => setBusy(false));
        }}
      />
      <Hint>{status}</Hint>
      <ErrorText>{error}</ErrorText>
      {entries.map((entry) => (
        <View
          key={entry.id}
          style={{
            gap: 8,
            paddingVertical: 16,
            borderBottomWidth: 1,
            borderBottomColor: theme.separator,
          }}
        >
          <Text
            style={{
              fontSize: 28,
              color: theme.label,
              textAlign: "right",
              writingDirection: "rtl",
            }}
          >
            {entry.arabic}
          </Text>
          <Text style={{ color: theme.label }}>{entry.meaning}</Text>
          <Button
            label="View available forms"
            kind="text"
            onPress={() => {
              api
                .json<DictionaryEntry>(
                  "/api/items?action=dictionary-entry&id=" + entry.id,
                )
                .then((detail) =>
                  setEntries((old) =>
                    old.map((e) => (e.id === detail.id ? detail : e)),
                  ),
                )
                .catch((err: unknown) =>
                  setError(
                    err instanceof Error ? err.message : "Could not load forms",
                  ),
                );
            }}
          />
          {entry.notice ? <Hint>{entry.notice}</Hint> : null}
          {entry.forms.map((f, index) => (
            <View key={index} style={{ gap: 4 }}>
              <Text
                style={{ color: theme.label, fontSize: 20, textAlign: "right" }}
              >
                {f.arabic}
              </Text>
              <Hint>
                {f.translit} · {f.conjugation} · {f.dialect}
              </Hint>
              <Button
                label="Save this form"
                kind="text"
                onPress={() => {
                  api
                    .post("/api/items", {
                      action: "save-dictionary",
                      entry_id: entry.id,
                      form_index: index,
                    })
                    .then(() => {
                      setStatus("Saved to your words.");
                      onSaved();
                    })
                    .catch((err: unknown) =>
                      setError(
                        err instanceof Error ? err.message : "Could not save",
                      ),
                    );
                }}
              />
            </View>
          ))}
          <Button
            label="Save headword to Words"
            kind="tint"
            onPress={() => {
              api
                .post("/api/items", {
                  action: "save-dictionary",
                  entry_id: entry.id,
                })
                .then(() => {
                  setStatus("Saved to your words.");
                  onSaved();
                })
                .catch((err: unknown) =>
                  setError(
                    err instanceof Error ? err.message : "Could not save",
                  ),
                );
            }}
          />
          <Button
            label="Source: Arwords"
            kind="text"
            onPress={() => {
              void Linking.openURL(entry.url);
            }}
          />
        </View>
      ))}
    </>
  );
}
