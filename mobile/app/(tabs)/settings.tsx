import { useAuth, useClerk, useUser } from "@clerk/expo";
import * as WebBrowser from "expo-web-browser";
import { useState } from "react";
import { Text, View } from "react-native";

import { BodyScroll, Button, ErrorText, Field, Hint, Screen } from "@/src/components/ui";
import { UI } from "@/src/copy";
import { useSession } from "@/src/session";
import { useTheme } from "@/src/theme";

export default function SettingsScreen() {
  const theme = useTheme();
  const session = useSession();
  const [languageError, setLanguageError] = useState("");
  const [server, setServer] = useState(session.apiUrl);
  const [serverError, setServerError] = useState("");

  return (
    <Screen title={UI.tabSettings}>
      <BodyScroll>
        {session.authRequired ? <ClerkAccount /> : <LocalAccount />}
        <View style={{ gap: 10, marginTop: 28 }}>
          <Text style={{ color: theme.label, fontSize: 22, fontWeight: "600" }}>{UI.language}</Text>
          <Hint>{UI.languageHint}</Hint>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
            <LanguageButton
              label="Levantine Arabic"
              selected={session.language === "arabic"}
              onPress={() => {
                setLanguageError("");
                session.setLanguage("arabic").catch((err: Error) => {
                  setLanguageError(err.message || UI.couldNotSaveLanguage);
                });
              }}
            />
            <LanguageButton
              label="Japanese"
              selected={session.language === "japanese"}
              onPress={() => {
                setLanguageError("");
                session.setLanguage("japanese").catch((err: Error) => {
                  setLanguageError(err.message || UI.couldNotSaveLanguage);
                });
              }}
            />
          </View>
          <ErrorText>{languageError}</ErrorText>
        </View>
        <View style={{ gap: 10, marginTop: 28 }}>
          <Text style={{ color: theme.label, fontSize: 22, fontWeight: "600" }}>{UI.server}</Text>
          <Hint>{UI.serverHint}</Hint>
          <Field
            label="Address"
            value={server}
            onChangeText={setServer}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            placeholder={UI.serverPlaceholder}
          />
          <Button
            kind="secondary"
            label={UI.saveServer}
            onPress={() => {
              setServerError("");
              session.replaceServer(server).catch((err: Error) => setServerError(err.message));
            }}
          />
          <ErrorText>{serverError}</ErrorText>
        </View>
      </BodyScroll>
    </Screen>
  );
}

function LanguageButton({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  const theme = useTheme();
  return (
    <Text
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected }}
      style={{
        overflow: "hidden",
        backgroundColor: selected ? theme.blue : theme.fill,
        color: selected ? "#ffffff" : theme.label,
        fontWeight: "600",
        paddingHorizontal: 14,
        paddingVertical: 10,
        borderRadius: 8,
      }}
    >
      {label}
    </Text>
  );
}

function LocalAccount() {
  const theme = useTheme();
  return (
    <View style={{ gap: 8 }}>
      <Text style={{ color: theme.label, fontSize: 22, fontWeight: "600" }}>{UI.account}</Text>
      <Hint>{UI.accountLocal}</Hint>
    </View>
  );
}

function ClerkAccount() {
  const theme = useTheme();
  const { user } = useUser();
  const { signOut } = useAuth();
  const clerk = useClerk();
  const [error, setError] = useState("");
  const email = user?.primaryEmailAddress?.emailAddress || user?.fullName || UI.signedIn;

  return (
    <View style={{ gap: 8 }}>
      <Text style={{ color: theme.label, fontSize: 22, fontWeight: "600" }}>{UI.account}</Text>
      <Hint>{email}</Hint>
      <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap" }}>
        <Button
          label={UI.manageAccount}
          onPress={() => {
            setError("");
            const url = safeProfileUrl(clerk);
            if (url) {
              WebBrowser.openBrowserAsync(url).catch((err: Error) => setError(err.message));
              return;
            }
            try {
              clerk.openUserProfile();
            } catch (err) {
              setError(err instanceof Error ? err.message : "Open Sawt on the web to manage this account.");
            }
          }}
        />
        <Button
          kind="secondary"
          label={UI.signOut}
          onPress={() => {
            setError("");
            signOut().catch((err: Error) => setError(err.message));
          }}
        />
      </View>
      <ErrorText>{error}</ErrorText>
      <Text style={{ color: theme.tertiary, fontSize: 12 }}>
        Sign-in uses the same Clerk account as the website.
      </Text>
    </View>
  );
}

function safeProfileUrl(clerk: { buildUserProfileUrl?: () => string }): string {
  try {
    const url = clerk.buildUserProfileUrl?.() || "";
    return url.startsWith("http") ? url : "";
  } catch {
    return "";
  }
}
