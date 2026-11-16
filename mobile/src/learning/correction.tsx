import { useState } from "react";
import * as Crypto from "expo-crypto";
import { Button, ErrorText, Field } from "@/src/components/ui";
import Hint from "./hint";
import { useSession } from "@/src/session";

export default function Correction({
  attemptId,
  onSaved,
}: {
  attemptId: number;
  onSaved: () => Promise<void>;
}) {
  const { api } = useSession();
  const [open, setOpen] = useState(false),
    [text, setText] = useState(""),
    [note, setNote] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return open ? (
    <>
      <Field
        label="Corrected sentences"
        value={text}
        onChangeText={setText}
        multiline
      />
      <Field
        label="What changed and why?"
        value={note}
        onChangeText={setNote}
        multiline
      />
      <Hint>Recorded as teacher notes entered by you.</Hint>
      <ErrorText>{error}</ErrorText>
      <Button
        label="Save correction"
        disabled={busy}
        kind="tint"
        onPress={() => {
          setBusy(true);
          api
            .post("/api/lessons", {
              action: "correction",
              request_id: Crypto.randomUUID(),
              attempt_id: attemptId,
              text,
              note,
              author: "Teacher notes entered by me",
            })
            .then(onSaved)
            .catch((err: unknown) =>
              setError(err instanceof Error ? err.message : "Could not save"),
            )
            .finally(() => setBusy(false));
        }}
      />
    </>
  ) : (
    <Button
      label="Add teacher correction"
      kind="text"
      onPress={() => setOpen(true)}
    />
  );
}
