import { useHostedAuth } from "@clerk/expo/hosted-auth";
import { useState } from "react";
import { Text, View } from "react-native";

import { Button, ErrorText, Field } from "@/src/components/ui";
import { UI, brandMark } from "@/src/copy";
import { cleanServerUrl } from "@/src/logic";
import { useSession } from "@/src/session";
import { useTheme } from "@/src/theme";

export function SignInGate() {
  const theme = useTheme();
  const { language } = useSession();
  const { startHostedAuth } = useHostedAuth();
  const [error, setError] = useState("");
  return (
    <View style={{ flex: 1, backgroundColor: theme.window, alignItems: "center", justifyContent: "center", padding: 28, gap: 14 }}>
      <Text style={{ fontSize: 42, color: theme.label }} accessibilityLabel="Sawt">
        {brandMark(language)}
      </Text>
      <Text style={{ color: theme.secondary, textAlign: "center", maxWidth: 320, fontSize: 16, lineHeight: 22 }}>{UI.gateBody}</Text>
      <Button
        label={UI.signIn}
        onPress={() => {
          setError("");
          startHostedAuth({ mode: "sign-in" }).catch((err: Error) => {
            setError(err.message || "Could not start sign-in.");
          });
        }}
      />
      <ErrorText>{error}</ErrorText>
    </View>
  );
}

export function ServerSetup({
  initial = "",
  error,
  onSave,
}: {
  initial?: string;
  error?: string;
  onSave: (url: string) => void;
}) {
  const theme = useTheme();
  const [value, setValue] = useState(initial);
  const [localError, setLocalError] = useState("");
  return (
    <View style={{ flex: 1, backgroundColor: theme.window, justifyContent: "center", padding: 28, gap: 12 }}>
      <Text style={{ fontSize: 42, color: theme.label }}>صوت</Text>
      <Text style={{ color: theme.label, fontSize: 22, fontWeight: "600" }}>Connect to Sawt</Text>
      <Text style={{ color: theme.secondary, fontSize: 16, lineHeight: 22 }}>
        Paste the address of your Sawt website. The app uses that server for your words, sign-in, and practice.
      </Text>
      <Field
        label="Server"
        value={value}
        onChangeText={setValue}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="url"
        placeholder={UI.serverPlaceholder}
      />
      <Button
        label={UI.saveServer}
        onPress={() => {
          const url = cleanServerUrl(value);
          if (!/^https?:\/\//i.test(url)) {
            setLocalError("Start the address with https://");
            return;
          }
          setLocalError("");
          onSave(url);
        }}
      />
      <ErrorText>{localError || error}</ErrorText>
    </View>
  );
}
