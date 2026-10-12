import { createContext, useContext, type ReactNode } from "react";
import { useColorScheme } from "react-native";

export type Palette = {
  scheme: "light" | "dark";
  label: string;
  secondary: string;
  tertiary: string;
  separator: string;
  blue: string;
  blueText: string;
  green: string;
  orange: string;
  red: string;
  grouped: string;
  fill: string;
  fillPressed: string;
  window: string;
  field: string;
  switchOn: string;
  reading: string;
};

const light: Palette = {
  scheme: "light",
  label: "#000000",
  secondary: "rgba(60, 60, 67, 0.6)",
  tertiary: "rgba(60, 60, 67, 0.3)",
  separator: "#c6c6c8",
  blue: "#007aff",
  blueText: "#0040dd",
  green: "#248a3d",
  orange: "#c93400",
  red: "#d70015",
  grouped: "#f2f2f7",
  fill: "#e5e5ea",
  fillPressed: "#d1d1d6",
  window: "#ffffff",
  field: "#ffffff",
  switchOn: "#34c759",
  reading: "Georgia",
};

const dark: Palette = {
  scheme: "dark",
  label: "#ffffff",
  secondary: "rgba(235, 235, 245, 0.6)",
  tertiary: "rgba(235, 235, 245, 0.3)",
  separator: "#38383a",
  blue: "#0a84ff",
  blueText: "#409cff",
  green: "#30d158",
  orange: "#ff9f0a",
  red: "#ff453a",
  grouped: "#000000",
  fill: "#2c2c2e",
  fillPressed: "#3a3a3c",
  window: "#1c1c1e",
  field: "#2c2c2e",
  switchOn: "#30d158",
  reading: "Georgia",
};

const ThemeContext = createContext<Palette>(light);

export function AppTheme({ children }: { children: ReactNode }) {
  const scheme = useColorScheme();
  const palette = scheme === "dark" ? dark : light;
  return <ThemeContext.Provider value={palette}>{children}</ThemeContext.Provider>;
}

export function useTheme(): Palette {
  return useContext(ThemeContext);
}
