import { ClerkProvider, useAuth, useUser } from "@clerk/expo";
import { tokenCache } from "@clerk/expo/token-cache";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { useCallback, useEffect, useState, type ReactNode } from "react";

import { fetchConfig } from "@/src/api";
import { Loading } from "@/src/components/ui";
import { ServerSetup, SignInGate } from "@/src/components/gate";
import { PracticeProvider } from "@/src/practice";
import { SessionProvider } from "@/src/session";
import { AppTheme, useTheme } from "@/src/theme";
import type { ServerConfig } from "@/src/types";

export { ErrorBoundary } from "expo-router";

const SERVER_KEY = "sawt.apiUrl";

SplashScreen.preventAutoHideAsync().catch(() => {});

export default function RootLayout() {
  return (
    <AppTheme>
      <Boot />
    </AppTheme>
  );
}

function Boot() {
  const theme = useTheme();
  const [booted, setBooted] = useState(false);
  const [apiUrl, setApiUrl] = useState<string | null>(null);
  const [config, setConfig] = useState<ServerConfig | null>(null);
  const [configError, setConfigError] = useState("");

  useEffect(() => {
    let cancelled = false;
    AsyncStorage.getItem(SERVER_KEY)
      .then((stored) => {
        if (cancelled) return;
        const env = (process.env.EXPO_PUBLIC_API_URL || "").trim().replace(/\/+$/, "");
        setApiUrl((stored || env || "").trim());
        setBooted(true);
      })
      .catch(() => {
        if (!cancelled) {
          setApiUrl("");
          setBooted(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!booted) return;
    SplashScreen.hideAsync().catch(() => {});
  }, [booted]);

  useEffect(() => {
    if (!apiUrl) return;
    let cancelled = false;
    setConfig(null);
    setConfigError("");
    fetchConfig(apiUrl)
      .then((payload) => {
        if (!cancelled) setConfig(payload);
      })
      .catch((error: Error) => {
        if (!cancelled) setConfigError(error.message);
      });
    return () => {
      cancelled = true;
    };
  }, [apiUrl]);

  const replaceServer = useCallback(async (url: string) => {
    const clean = url.trim().replace(/\/+$/, "");
    await AsyncStorage.setItem(SERVER_KEY, clean);
    setApiUrl(clean);
    setConfig(null);
  }, []);

  if (!booted || apiUrl === null) return <Loading />;
  if (!apiUrl) return <ServerSetup onSave={(url) => void replaceServer(url)} />;
  if (configError) return <ServerSetup initial={apiUrl} error={configError} onSave={(url) => void replaceServer(url)} />;
  if (!config) return <Loading label="Connecting" />;

  const serverKey = (config.clerkPublishableKey || "").trim();
  const envKey = (process.env.EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY || "").trim();
  const publishableKey = serverKey || (config.authRequired === false ? "" : envKey);
  const authRequired = Boolean(publishableKey);

  const navigationTheme = theme.scheme === "dark" ? DarkTheme : DefaultTheme;
  const shell = (
    <ThemeProvider
      value={{
        ...navigationTheme,
        colors: {
          ...navigationTheme.colors,
          background: theme.window,
          card: theme.grouped,
          text: theme.label,
          border: theme.separator,
          primary: theme.blue,
        },
      }}
    >
      <StatusBar style={theme.scheme === "dark" ? "light" : "dark"} />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="(tabs)" />
      </Stack>
    </ThemeProvider>
  );

  if (!authRequired) {
    return (
      <SessionProvider
        apiUrl={apiUrl}
        getToken={readAnonymousToken}
        authRequired={false}
        accountEmail=""
        authReady
        signedIn
        replaceServer={replaceServer}
      >
        <PracticeProvider>{shell}</PracticeProvider>
      </SessionProvider>
    );
  }

  return (
    <ClerkProvider publishableKey={publishableKey} tokenCache={tokenCache}>
      <ClerkShell apiUrl={apiUrl} replaceServer={replaceServer}>
        {shell}
      </ClerkShell>
    </ClerkProvider>
  );
}

async function readAnonymousToken() {
  return null;
}

function ClerkShell({
  apiUrl,
  replaceServer,
  children,
}: {
  apiUrl: string;
  replaceServer: (url: string) => Promise<void>;
  children: ReactNode;
}) {
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const { user } = useUser();
  const email = user?.primaryEmailAddress?.emailAddress || user?.fullName || "";
  const readToken = useCallback(async () => {
    try {
      return (await getToken()) ?? null;
    } catch {
      return null;
    }
  }, [getToken]);
  if (!isLoaded) return <Loading />;
  return (
    <SessionProvider
      apiUrl={apiUrl}
      getToken={readToken}
      authRequired
      accountEmail={email}
      authReady={isLoaded}
      signedIn={Boolean(isSignedIn)}
      replaceServer={replaceServer}
    >
      {isSignedIn ? <PracticeProvider>{children}</PracticeProvider> : <SignInGate />}
    </SessionProvider>
  );
}
