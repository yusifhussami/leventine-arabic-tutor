import { brandMark } from "@/src/copy";
import { useSession } from "@/src/session";
import { useTheme } from "@/src/theme";
import * as Haptics from "expo-haptics";
import { type ReactNode, type Ref, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Animated,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type TextInputProps,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

export function Screen({
  title,
  children,
  background,
  footer,
}: {
  title: string;
  children: ReactNode;
  background?: "window" | "grouped";
  footer?: ReactNode;
}) {
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const fill = background === "grouped" ? theme.grouped : theme.window;
  return (
    <View style={{ flex: 1, backgroundColor: fill, paddingTop: insets.top }}>
      <Header title={title} />
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={insets.top + 48}
      >
        {children}
        {footer}
      </KeyboardAvoidingView>
    </View>
  );
}

export function Header({ title, children }: { title: string; children?: ReactNode }) {
  const theme = useTheme();
  const { language } = useSession();
  const mark = brandMark(language);
  const opacity = useRef(new Animated.Value(1)).current;
  const shown = useRef(mark);
  const [text, setText] = useState(mark);

  useEffect(() => {
    if (shown.current === mark) return;
    shown.current = mark;
    Animated.timing(opacity, { toValue: 0, duration: 140, useNativeDriver: true }).start(() => {
      setText(mark);
      Animated.timing(opacity, { toValue: 1, duration: 180, useNativeDriver: true }).start();
    });
  }, [mark, opacity]);

  return (
    <View style={[styles.header, { backgroundColor: theme.grouped, borderBottomColor: theme.separator }]}>
      <Animated.Text style={[styles.brand, { color: theme.label, opacity }]} accessibilityLabel="Sawt">
        {text}
      </Animated.Text>
      <Text style={[styles.title, { color: theme.label }]}>{title}</Text>
      <View style={styles.headerEnd}>
        {children}
        <Sky />
      </View>
    </View>
  );
}

export function Sky() {
  const theme = useTheme();
  const dark = theme.scheme === "dark";
  return (
    <View style={styles.sky} accessibilityElementsHidden>
      {dark ? (
        <View style={[styles.moon, { borderColor: theme.label }]} />
      ) : (
        <View style={[styles.sun, { borderColor: "#ffcc00" }]} />
      )}
    </View>
  );
}

export function Button({
  label,
  onPress,
  kind = "primary",
  disabled,
}: {
  label: string;
  onPress: () => void;
  kind?: "primary" | "secondary" | "tint" | "text";
  disabled?: boolean;
}) {
  const theme = useTheme();
  const filled = kind === "primary" || kind === "tint";
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={() => {
        void Haptics.selectionAsync();
        onPress();
      }}
      style={({ pressed }) => [
        kind === "text" ? styles.textButton : styles.button,
        kind !== "text" && {
          backgroundColor: filled
            ? pressed
              ? theme.blueText
              : theme.blue
            : pressed
              ? theme.fillPressed
              : theme.fill,
        },
        disabled && { opacity: 0.45 },
      ]}
    >
      <Text
        style={{
          color: kind === "text" ? theme.blueText : filled ? "#ffffff" : theme.label,
          fontWeight: "600",
          fontSize: kind === "text" ? 15 : 16,
        }}
      >
        {label}
      </Text>
    </Pressable>
  );
}

export function Field({
  label,
  inputRef,
  ...props
}: TextInputProps & { label?: string; multiline?: boolean; inputRef?: Ref<TextInput> }) {
  const theme = useTheme();
  return (
    <View style={{ gap: 6 }}>
      {label ? <Text style={[styles.label, { color: theme.secondary }]}>{label}</Text> : null}
      <TextInput
        ref={inputRef}
        placeholderTextColor={theme.tertiary}
        autoCorrect={false}
        autoCapitalize="none"
        spellCheck={false}
        {...props}
        style={[
          styles.input,
          {
            color: theme.label,
            backgroundColor: theme.field,
            borderColor: theme.separator,
            minHeight: props.multiline ? 160 : 44,
            textAlignVertical: props.multiline ? "top" : "center",
          },
          props.style,
        ]}
      />
    </View>
  );
}

export function ErrorText({ children, note }: { children?: string; note?: boolean }) {
  const theme = useTheme();
  if (!children) return null;
  return <Text style={{ color: note ? theme.secondary : theme.red, fontSize: 13 }}>{children}</Text>;
}

export function Hint({ children }: { children: string }) {
  const theme = useTheme();
  return <Text style={{ color: theme.secondary, fontSize: 15, lineHeight: 21 }}>{children}</Text>;
}

export function Chip({
  label,
  selected,
  onPress,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
}) {
  const theme = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={() => {
        void Haptics.selectionAsync();
        onPress();
      }}
      style={({ pressed }) => ({
        minHeight: 40,
        paddingHorizontal: 14,
        borderRadius: 8,
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: selected ? theme.blue : pressed ? theme.fillPressed : theme.fill,
      })}
    >
      <Text style={{ color: selected ? "#ffffff" : theme.label, fontWeight: "600", fontSize: 15 }}>{label}</Text>
    </Pressable>
  );
}

export function BodyScroll({ children }: { children: ReactNode }) {
  return (
    <ScrollView
      contentInsetAdjustmentBehavior="never"
      keyboardShouldPersistTaps="handled"
      contentContainerStyle={{ padding: 20, paddingBottom: 40, gap: 14 }}
    >
      {children}
    </ScrollView>
  );
}

export function Loading({ label }: { label?: string }) {
  const theme = useTheme();
  return (
    <View style={[styles.center, { backgroundColor: theme.window }]}>
      <ActivityIndicator color={theme.blue} />
      {label ? <Text style={{ color: theme.secondary }}>{label}</Text> : null}
    </View>
  );
}

export function Orb({
  phase,
  volume,
  onPress,
  label,
}: {
  phase: "idle" | "listening" | "speaking";
  volume: number;
  onPress: () => void;
  label: string;
}) {
  const theme = useTheme();
  const scale = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    if (phase === "speaking") {
      const loop = Animated.loop(
        Animated.sequence([
          Animated.timing(scale, { toValue: 1.08, duration: 680, useNativeDriver: true }),
          Animated.timing(scale, { toValue: 0.96, duration: 680, useNativeDriver: true }),
        ]),
      );
      loop.start();
      return () => loop.stop();
    }
    const target = phase === "listening" ? 1 + volume * 0.22 : 1;
    Animated.spring(scale, { toValue: target, friction: 6, tension: 80, useNativeDriver: true }).start();
    return undefined;
  }, [phase, scale, volume]);

  const dark = theme.scheme === "dark";
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress} style={styles.orbHit}>
      <Animated.View
        style={[
          styles.orb,
          {
            backgroundColor: dark ? "#0b0b0d" : "#ececf0",
            transform: [{ scale }],
          },
        ]}
      >
        <View style={[styles.blob, styles.blobA, { backgroundColor: theme.blue, opacity: phase === "idle" ? 0.85 : 1 }]} />
        <View style={[styles.blob, styles.blobB]} />
        <View style={[styles.blob, styles.blobC, { opacity: dark ? 0.55 : 0.7 }]} />
      </Animated.View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  header: {
    minHeight: 48,
    paddingHorizontal: 16,
    borderBottomWidth: StyleSheet.hairlineWidth,
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  brand: { fontSize: 22, fontWeight: "600" },
  title: { fontSize: 17, fontWeight: "600" },
  headerEnd: { marginLeft: "auto", flexDirection: "row", alignItems: "center", gap: 10 },
  sky: { width: 18, height: 18, alignItems: "center", justifyContent: "center" },
  sun: { width: 12, height: 12, borderRadius: 6, borderWidth: 1.5 },
  moon: { width: 12, height: 12, borderRadius: 6, borderWidth: 1.5, borderRightWidth: 0 },
  button: {
    minHeight: 44,
    paddingHorizontal: 16,
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
  },
  textButton: { minHeight: 44, justifyContent: "center", paddingHorizontal: 4 },
  label: { fontSize: 13, fontWeight: "600" },
  input: {
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 16,
  },
  center: { flex: 1, alignItems: "center", justifyContent: "center", gap: 12 },
  orbHit: { alignItems: "center", justifyContent: "center" },
  orb: {
    width: 220,
    height: 220,
    borderRadius: 110,
    overflow: "hidden",
  },
  blob: { position: "absolute", borderRadius: 999 },
  blobA: { width: 140, height: 140, left: 40, top: 40 },
  blobB: { width: 120, height: 120, left: 22, top: 70, backgroundColor: "#5ac8fa" },
  blobC: { width: 90, height: 90, left: 70, top: 24, backgroundColor: "#ffffff" },
});
