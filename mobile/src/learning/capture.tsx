import { useState } from "react";
import { View } from "react-native";
import * as Crypto from "expo-crypto";
import { Button, ErrorText, Field } from "@/src/components/ui";
import Hint from "./hint";
import { useSession } from "@/src/session";
import { isoDay } from "@/src/logic";
import type { RuleSeed } from "@/src/learning";
import Title from "./title";

export default function Capture({
  teacher,
  seed,
  onSaved,
}: {
  teacher: string;
  seed?: RuleSeed;
  onSaved: (id: number) => Promise<void>;
}) {
  const { api } = useSession();
  const [title, setTitle] = useState(""),
    [date, setDate] = useState(isoDay(new Date())),
    [name, setName] = useState(teacher),
    [goal, setGoal] = useState(""),
    [words, setWords] = useState(""),
    [prompt, setPrompt] = useState(""),
    [count, setCount] = useState("3"),
    [due, setDue] = useState(""),
    [notes, setNotes] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [rules, setRules] = useState([
    {
      title: seed?.title || "",
      explanation: seed?.explanation || "",
      example: "",
      source: seed?.source || "Teacher lesson",
    },
  ]);
  const updateRule = (
    index: number,
    key: "title" | "explanation" | "example" | "source",
    value: string,
  ) =>
    setRules((old) =>
      old.map((rule, i) => (i === index ? { ...rule, [key]: value } : rule)),
    );
  return (
    <>
      <Title>Capture the lesson</Title>
      <Field label="Lesson title" value={title} onChangeText={setTitle} />
      <Field
        label="Lesson date (YYYY-MM-DD)"
        value={date}
        onChangeText={setDate}
      />
      <Field label="Teacher" value={name} onChangeText={setName} />
      <Field
        label="What do you want to be able to say?"
        value={goal}
        onChangeText={setGoal}
        multiline
      />
      <Title>Words</Title>
      <Hint>
        Use word = meaning. Words already in your notebook will be reused.
      </Hint>
      <Field
        label="Vocabulary"
        value={words}
        onChangeText={setWords}
        multiline
      />
      <Title>Grammar to use</Title>
      {rules.map((rule, index) => (
        <View key={index} style={{ gap: 10 }}>
          <Field
            label="Rule or pattern"
            value={rule.title}
            onChangeText={(value) => updateRule(index, "title", value)}
          />
          <Field
            label="How it works"
            value={rule.explanation}
            onChangeText={(value) => updateRule(index, "explanation", value)}
            multiline
          />
          <Field
            label="Example"
            value={rule.example}
            onChangeText={(value) => updateRule(index, "example", value)}
            multiline
          />
          <Field
            label="Source / book page"
            value={rule.source}
            onChangeText={(value) => updateRule(index, "source", value)}
          />
          <Button
            label="Remove rule"
            kind="text"
            onPress={() => setRules((old) => old.filter((_, i) => i !== index))}
          />
        </View>
      ))}
      <Button
        label="Add another rule"
        kind="text"
        onPress={() =>
          setRules((old) => [
            ...old,
            {
              title: "",
              explanation: "",
              example: "",
              source: "Teacher lesson",
            },
          ])
        }
      />
      <Field
        label="Other lesson notes"
        value={notes}
        onChangeText={setNotes}
        multiline
      />
      <Title>Sentence homework</Title>
      <Field
        label="Teacher’s brief (optional)"
        value={prompt}
        onChangeText={setPrompt}
        multiline
      />
      <Hint>Leave blank to build a brief from your words, rule, and goal.</Hint>
      <Field
        label="Number of sentences"
        value={count}
        onChangeText={setCount}
        keyboardType="number-pad"
      />
      <Field
        label="Due date (optional YYYY-MM-DD)"
        value={due}
        onChangeText={setDue}
      />
      <ErrorText>{error}</ErrorText>
      <Button
        label={busy ? "Saving…" : "Save lesson and open workshop"}
        disabled={busy}
        onPress={() => {
          setBusy(true);
          setError("");
          api
            .post<{ task_id: number }>("/api/lessons", {
              action: "capture",
              request_id: Crypto.randomUUID(),
              title,
              learned_on: date,
              teacher: name,
              goal,
              words_text: words,
              rules: rules.filter((rule) => rule.title || rule.explanation),
              prompt,
              sentence_count: Number(count),
              due_on: due,
              notes,
            })
            .then((r) => onSaved(r.task_id))
            .catch((err: unknown) =>
              setError(
                err instanceof Error
                  ? err.message
                  : "Could not save. Your lesson is still here.",
              ),
            )
            .finally(() => setBusy(false));
        }}
      />
    </>
  );
}
