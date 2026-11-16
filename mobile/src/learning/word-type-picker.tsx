import { useState } from "react";
import { View } from "react-native";
import { Button, ErrorText } from "@/src/components/ui";
import { useSession } from "@/src/session";
export type WordCategory =
  "" | "noun" | "adjective" | "imperative" | "verb" | "phrase" | "other";
export type WordClasses = {
  labels: Record<string, string>;
  assignments: Record<string, WordCategory>;
};
export const WORD_TYPE_CHOICES: [WordCategory, string][] = [
  ["", "Unsorted"],
  ["noun", "Nouns"],
  ["adjective", "Adjectives"],
  ["imperative", "Imperatives / commands"],
  ["verb", "Other verbs"],
  ["phrase", "Phrases"],
  ["other", "Other"],
];
export default function WordTypePicker({
  itemId,
  category,
  onSaved,
}: {
  itemId: number;
  category: WordCategory;
  onSaved: (data: WordClasses) => void;
}) {
  const { api } = useSession();
  const [open, setOpen] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  return (
    <View style={{ gap: 6 }}>
      <Button
        label={`Type: ${WORD_TYPE_CHOICES.find(([value]) => value === category)?.[1] || "Unsorted"}`}
        kind="text"
        disabled={busy}
        onPress={() => setOpen((old) => !old)}
      />
      {open ? (
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}>
          {WORD_TYPE_CHOICES.map(([value, label]) => (
            <Button
              key={value}
              label={label}
              kind={value === category ? "tint" : "secondary"}
              disabled={busy}
              onPress={() => {
                setBusy(true);
                setError("");
                api
                  .post<WordClasses>("/api/items", {
                    action: "classify-word",
                    item_id: itemId,
                    category: value,
                  })
                  .then((data) => {
                    onSaved(data);
                    setOpen(false);
                  })
                  .catch((err: unknown) =>
                    setError(
                      err instanceof Error
                        ? err.message
                        : "Could not save the word type",
                    ),
                  )
                  .finally(() => setBusy(false));
              }}
            />
          ))}
        </View>
      ) : null}
      <ErrorText>{error}</ErrorText>
    </View>
  );
}
