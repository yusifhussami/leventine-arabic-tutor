import type { ReactNode } from "react";
import { Text } from "react-native";
import { useTheme } from "@/src/theme";

export default function Title({ children }: { children: ReactNode }) {
  const theme = useTheme();
  return (
    <Text
      style={{
        fontSize: 20,
        fontWeight: "600",
        color: theme.label,
        marginTop: 20,
      }}
    >
      {children}
    </Text>
  );
}
