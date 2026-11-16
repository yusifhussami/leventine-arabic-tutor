import { useEffect, useRef, useState } from "react";
import { ScrollView, Text, TextInput, View } from "react-native";

import { Button, ErrorText, Field, Orb, Screen } from "@/src/components/ui";
import { UI, copy } from "@/src/copy";
import { usePractice } from "@/src/practice";
import { useSession } from "@/src/session";
import { useTheme } from "@/src/theme";

const SCENES = [
  ["coffee", UI.sceneCoffee],
  ["restaurant", UI.sceneRestaurant],
  ["shop", UI.sceneShop],
  ["taxi", UI.sceneTaxi],
] as const;

export default function PracticeScreen() {
  const theme = useTheme();
  const { language } = useSession();
  const practice = usePractice();
  const scrollRef = useRef<ScrollView>(null);
  const sentenceY = useRef(0);
  const sentenceRef = useRef<TextInput>(null);
  const [typed, setTyped] = useState("");
  const typedRef = useRef<TextInput>(null);
  useEffect(() => {
    if (practice.error === UI.noSpeech) typedRef.current?.focus();
  }, [practice.error]);
  useEffect(() => {
    if (!practice.activeWord) return;
    const timer = setTimeout(() => {
      scrollRef.current?.scrollTo({ y: Math.max(0, sentenceY.current - 12), animated: true });
      sentenceRef.current?.focus();
    }, 250);
    return () => clearTimeout(timer);
  }, [practice.activeWord?.id]);
  const stateLabel =
    practice.phase === "listening" ? UI.listening : practice.phase === "speaking" ? UI.speaking : UI.tapToTalk;

  return (
    <Screen title={UI.tabPractice}>
      <ScrollView
        ref={scrollRef}
        keyboardShouldPersistTaps="handled"
        contentInsetAdjustmentBehavior="never"
        contentContainerStyle={{ padding: 20, paddingBottom: 48, gap: 16, alignItems: "center" }}
      >
        <Orb phase={practice.phase} volume={practice.volume} onPress={practice.toggleOrb} label={stateLabel} />
        <Text style={{ color: theme.secondary, fontSize: 15 }}>{stateLabel}</Text>
        {practice.line ? (
          <Text
            style={{
              fontFamily: theme.reading,
              fontSize: 28,
              lineHeight: 34,
              textAlign: "center",
              color: theme.label,
            }}
          >
            {practice.line}
          </Text>
        ) : null}
        {practice.gloss ? (
          <Text style={{ color: theme.secondary, fontSize: 16, textAlign: "center" }}>{practice.gloss}</Text>
        ) : null}
        <ErrorText>{practice.error}</ErrorText>
        <View style={{ width: "100%", gap: 14 }}>
          {practice.log.map((turn) => (
            <View key={turn.id} style={{ gap: 2 }}>
              <Text style={{ color: theme.secondary, fontSize: 13 }}>{turn.who}</Text>
              <Text style={{ fontFamily: theme.reading, fontSize: 22, color: theme.label }}>{turn.line}</Text>
              {turn.gloss ? <Text style={{ color: theme.secondary }}>{turn.gloss}</Text> : null}
              {turn.note ? <Text style={{ color: theme.secondary, marginTop: 4 }}>{turn.note}</Text> : null}
            </View>
          ))}
        </View>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8, justifyContent: "center" }}>
          {SCENES.map(([id, label]) => (
            <ChipButton key={id} label={label} selected={practice.scene === id} onPress={() => practice.chooseScene(id)} />
          ))}
        </View>
        <View style={{ width: "100%" }}>
          <Field
            inputRef={typedRef}
            value={typed}
            onChangeText={setTyped}
            placeholder={copy(language, "typeArabizi")}
            onSubmitEditing={() => {
              practice.sendTyped(typed);
              setTyped("");
            }}
            blurOnSubmit={false}
            returnKeyType="send"
          />
        </View>
        <View
          onLayout={(event) => {
            sentenceY.current = event.nativeEvent.layout.y;
          }}
          style={{ width: "100%", gap: 12, marginTop: 8 }}
        >
          {practice.activeWord ? (
            <View style={{ gap: 12 }}>
              <Text style={{ color: theme.secondary, fontSize: 12, fontWeight: "600" }}>{UI.writeWith}</Text>
              <Text style={{ fontFamily: theme.reading, fontSize: 40, color: theme.label }}>{practice.activeWord.spelling}</Text>
              <Text style={{ color: theme.secondary, fontSize: 16 }}>{practice.activeWord.gloss}</Text>
              {practice.similar.map((match) => (
                <Text key={`${match.spelling}-${match.gloss}`} style={{ color: theme.label, paddingVertical: 6, borderTopWidth: 1, borderTopColor: theme.separator }}>
                  {match.spelling} · {match.gloss}
                </Text>
              ))}
              <Field
                inputRef={sentenceRef}
                label={UI.yourSentence}
                value={practice.sentence}
                onChangeText={practice.setSentence}
                placeholder={copy(language, "sentencePlaceholder")}
                onFocus={() => scrollRef.current?.scrollTo({ y: sentenceY.current, animated: true })}
              />
              <Button
                label={UI.checkSentence}
                disabled={practice.judging}
                onPress={() => {
                  void practice.checkSentence();
                }}
              />
              {practice.judgment.text ? (
                <Text
                  style={{
                    color: practice.judgment.tone === "ok" ? theme.green : theme.orange,
                    fontSize: 15,
                    lineHeight: 21,
                  }}
                >
                  {practice.judgment.text}
                </Text>
              ) : null}
            </View>
          ) : null}
        </View>
      </ScrollView>
    </Screen>
  );
}

function ChipButton({
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
    <Text
      onPress={onPress}
      style={{
        overflow: "hidden",
        backgroundColor: selected ? theme.blue : theme.fill,
        color: selected ? "#ffffff" : theme.label,
        fontWeight: "600",
        fontSize: 15,
        paddingHorizontal: 14,
        paddingVertical: 10,
        borderRadius: 8,
      }}
    >
      {label}
    </Text>
  );
}
