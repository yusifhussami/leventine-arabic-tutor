import type { ReactNode } from "react";
import { Text } from "react-native";
import { useTheme } from "@/src/theme";
export default function Hint({ children }: { children: ReactNode }) {
  const theme = useTheme();
  return (
    <Text style={{ color: theme.secondary, fontSize: 15, lineHeight: 21 }}>
      {children}
    </Text>
  );
}
