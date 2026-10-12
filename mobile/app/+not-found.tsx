import { Link, Stack } from "expo-router";
import { Text, View } from "react-native";

import { useTheme } from "@/src/theme";

export default function NotFoundScreen() {
  const theme = useTheme();
  return (
    <>
      <Stack.Screen options={{ title: "Sawt" }} />
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: theme.window, gap: 12 }}>
        <Text style={{ color: theme.label, fontSize: 18 }}>This screen doesn't exist.</Text>
        <Link href="/">
          <Text style={{ color: theme.blueText, fontWeight: "600" }}>Back to Today</Text>
        </Link>
      </View>
    </>
  );
}
