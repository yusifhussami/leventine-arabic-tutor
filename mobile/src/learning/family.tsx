import { useState } from "react";
import { Text, View } from "react-native";
import { Button, Field } from "@/src/components/ui";
import Hint from "./hint";
import { useSession } from "@/src/session";
import { useTheme } from "@/src/theme";
import { FORM_LABELS, type FamilyForm, type WordFamily } from "@/src/learning";
import Title from "./title";

export default function Family({ initial }: { initial: WordFamily }) {
  const { api } = useSession();
  const theme = useTheme();
  const [family, setFamily] = useState(initial),
    [forms, setForms] = useState(initial.forms),
    [kind, setKind] = useState<FamilyForm["kind"]>("past"),
    [arabic, setArabic] = useState(""),
    [arabizi, setArabizi] = useState(""),
    [meaning, setMeaning] = useState(""),
    [subject, setSubject] = useState(""),
    [example, setExample] = useState(""),
    [status, setStatus] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <>
      <Title>{family.item.spelling} · word family</Title>
      <Hint>
        Keep meanings and subjects separate. Continuous is a construction.
        Confirm related nouns and adjectives with your teacher.
      </Hint>
      {forms.map((f, i) => (
        <View
          key={i}
          style={{
            gap: 4,
            paddingVertical: 10,
            borderBottomColor: theme.separator,
            borderBottomWidth: 1,
          }}
        >
          <Text style={{ color: theme.label, fontWeight: "600" }}>
            {FORM_LABELS.find((x) => x.kind === f.kind)?.label} · {f.subject}
          </Text>
          <Text
            style={{ color: theme.label, fontSize: 24, textAlign: "right" }}
          >
            {f.arabic}
          </Text>
          <Hint>
            {f.arabizi} · {f.meaning}
          </Hint>
          <Hint>{f.example}</Hint>
          <Hint>
            {f.source === "suggestion" ? "AI suggestion — review" : f.source}
          </Hint>
          <Button
            label="Remove form"
            kind="text"
            onPress={() =>
              setForms((old) => old.filter((_, index) => index !== i))
            }
          />
        </View>
      ))}
      <Title>Add a teacher-confirmed form</Title>
      <View style={{ flexDirection: "row", gap: 6, flexWrap: "wrap" }}>
        {FORM_LABELS.map((choice) => (
          <Button
            key={choice.kind}
            label={choice.label}
            kind={kind === choice.kind ? "tint" : "secondary"}
            onPress={() => setKind(choice.kind)}
          />
        ))}
      </View>
      <Field
        label="Subject / gender / number"
        value={subject}
        onChangeText={setSubject}
      />
      <Field label="Arabic" value={arabic} onChangeText={setArabic} />
      <Field label="Arabizi" value={arabizi} onChangeText={setArabizi} />
      <Field
        label="Meaning of this form"
        value={meaning}
        onChangeText={setMeaning}
      />
      <Field
        label="Example"
        value={example}
        onChangeText={setExample}
        multiline
      />
      <Button
        label="Add form to editor"
        kind="secondary"
        onPress={() => {
          if (!arabic.trim() && !arabizi.trim()) {
            setStatus("Add an Arabic or Arabizi spelling.");
            return;
          }
          setForms((old) => [
            ...old,
            {
              kind,
              arabic,
              arabizi,
              meaning,
              subject,
              example,
              source: "teacher",
              source_url: "",
            },
          ]);
          setArabic("");
          setArabizi("");
          setExample("");
        }}
      />
      <Button
        label="Suggest related forms"
        disabled={busy}
        kind="text"
        onPress={() => {
          setBusy(true);
          api
            .post<{ forms: FamilyForm[]; notice: string }>("/api/items", {
              action: "suggest-family",
              item_id: family.item.id,
            })
            .then((r) => {
              setForms((old) => [...old, ...r.forms]);
              setStatus(r.notice);
            })
            .catch((err: unknown) =>
              setStatus(
                err instanceof Error
                  ? err.message
                  : "Could not load suggestions. Add confirmed forms manually.",
              ),
            )
            .finally(() => setBusy(false));
        }}
      />
      <Button
        label="Save word family"
        disabled={busy}
        onPress={() => {
          setBusy(true);
          api
            .post<WordFamily>("/api/items", {
              action: "save-family",
              item_id: family.item.id,
              revision: family.revision,
              forms,
            })
            .then((r) => {
              setFamily(r);
              setForms(r.forms);
              setStatus("Word family saved.");
            })
            .catch((err: unknown) =>
              setStatus(err instanceof Error ? err.message : "Could not save"),
            )
            .finally(() => setBusy(false));
        }}
      />
      <Hint>{status}</Hint>
    </>
  );
}
