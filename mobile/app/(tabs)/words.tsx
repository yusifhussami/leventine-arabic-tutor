import { router } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { Pressable, Text, TextInput, View } from "react-native";

import { loadItems, updateItem } from "@/src/api";
import { BodyScroll, Button, ErrorText, Hint, Screen } from "@/src/components/ui";
import { UI, copy, wordCount } from "@/src/copy";
import { formatDay, groupByDate } from "@/src/logic";
import { usePractice } from "@/src/practice";
import { useSession } from "@/src/session";
import { useTheme } from "@/src/theme";
import type { NotebookItem } from "@/src/types";

export default function WordsScreen() {
  const theme = useTheme();
  const { api, language, revision, touchLibrary } = useSession();
  const { patchWord } = usePractice();
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<NotebookItem[]>([]);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [spelling, setSpelling] = useState("");
  const [gloss, setGloss] = useState("");
  const [arabic, setArabic] = useState("");
  const [writing, setWriting] = useState<"all" | "arabic">("all");
  const [matching, setMatching] = useState(false);
  const [matchStatus, setMatchStatus] = useState("");
  const request = useRef(0);

  useEffect(() => {
    const handle = setTimeout(() => {
      const id = ++request.current;
      const q = query.trim();
      setError("");
      loadItems(api, q)
        .then((rows) => {
          if (id !== request.current) return;
          setItems(Array.isArray(rows) ? rows : []);
        })
        .catch((err: Error) => {
          if (id !== request.current) return;
          setError(err.message || UI.searchFailed);
        });
    }, 280);
    return () => clearTimeout(handle);
  }, [api, query, language, revision]);

  const searching = query.trim().length > 0;
  const groups = searching ? [] : groupByDate(items);

  return (
    <Screen title={UI.tabWords}>
      <View style={{ paddingHorizontal: 16, paddingTop: 12 }}>
        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder={UI.search}
          placeholderTextColor={theme.tertiary}
          autoCapitalize="none"
          autoCorrect={false}
          clearButtonMode="while-editing"
          accessibilityLabel={UI.search}
          style={{
            minHeight: 40,
            borderRadius: 8,
            borderWidth: 1,
            borderColor: theme.separator,
            backgroundColor: theme.field,
            color: theme.label,
            paddingHorizontal: 12,
            fontSize: 16,
          }}
        />
      </View>
      <BodyScroll>
        {language === "arabic" ? <Button label="Search the dictionary" kind="secondary" onPress={() => router.navigate({ pathname: "/learn", params: { view: "dictionary" } })} /> : null}
        {language === "arabic" ? (
          <View style={{ gap: 12 }}>
            <View style={{ flexDirection: "row", gap: 8 }}>
              <Button label="All words" kind={writing === "all" ? "tint" : "secondary"} onPress={() => setWriting("all")} />
              <Button label="Arabic spelling" kind={writing === "arabic" ? "tint" : "secondary"} onPress={() => setWriting("arabic")} />
            </View>
            {writing === "arabic" ? (
              <View style={{ gap: 8 }}>
                <Hint>Match saved and CSV-imported words with Arwords using Arabizi and meaning. Your edits are kept.</Hint>
                <Button label={matching ? "Matching…" : "Match my words"} disabled={matching} onPress={() => {
                  setMatching(true);
                  setMatchStatus("");
                  setError("");
                  api.post<{ matched: number; unchanged: number; unresolved: number }>("/api/items", { action: "match-arwords" })
                    .then((result) => {
                      setMatchStatus(`${result.matched} matched · ${result.unchanged} already saved or edited · ${result.unresolved} without a confident match`);
                      touchLibrary();
                    })
                    .catch((err: unknown) => setError(err instanceof Error ? err.message : "Could not match words. Try again."))
                    .finally(() => setMatching(false));
                }} />
                {matchStatus ? <Hint>{matchStatus}</Hint> : null}
              </View>
            ) : null}
          </View>
        ) : null}
        <ErrorText>{error}</ErrorText>
        {items.length === 0 ? (
          <View style={{ gap: 6 }}>
            <Text style={{ color: theme.secondary }}>{searching ? UI.noSearchMatches : UI.emptyLibrary}</Text>
            {!searching ? <Text style={{ color: theme.secondary }}>{UI.emptyLibraryHint}</Text> : null}
          </View>
        ) : (
          <Text style={{ color: theme.secondary }}>{wordCount(items.length)}</Text>
        )}
        {searching && items.length > 0 ? (
          <View style={{ gap: 4 }}>
            <Text style={{ color: theme.secondary, fontWeight: "600" }}>{UI.searchResults}</Text>
            {items.map((item) => (
              <WordRow
                key={item.id}
                item={item}
                editing={editing === item.id}
                spelling={spelling}
                gloss={gloss}
                arabic={arabic}
                arabicFirst={language === "arabic" && writing === "arabic"}
                onArabic={setArabic}
                onSpelling={setSpelling}
                onGloss={setGloss}
                onForms={() => router.navigate({ pathname: "/learn", params: { wordId: String(item.id) } })}
                onEdit={() => {
                  setEditing(item.id);
                  setSpelling(item.spelling);
                  setGloss(item.gloss);
                  setArabic(item.arabic_script || "");
                  setError("");
                }}
                onCancel={() => setEditing(null)}
                onSave={() => {
                  updateItem(api, item.id, spelling, gloss, language === "arabic" ? arabic : undefined)
                    .then((saved) => {
                      setEditing(null);
                      patchWord(item.id, saved.spelling || spelling, saved.gloss || gloss);
                      touchLibrary();
                    })
                    .catch((err: Error) => setError(err.message));
                }}
              />
            ))}
          </View>
        ) : null}
        {groups.map(([date, rows]) => (
          <View key={date} style={{ gap: 4 }}>
            <Text style={{ color: theme.secondary, fontWeight: "600", marginTop: 8 }}>{formatDay(date)}</Text>
            {rows.map((item) => (
              <WordRow
                key={item.id}
                item={item}
                editing={editing === item.id}
                spelling={spelling}
                gloss={gloss}
                arabic={arabic}
                arabicFirst={language === "arabic" && writing === "arabic"}
                onArabic={setArabic}
                onSpelling={setSpelling}
                onGloss={setGloss}
                onForms={() => router.navigate({ pathname: "/learn", params: { wordId: String(item.id) } })}
                onEdit={() => {
                  setEditing(item.id);
                  setSpelling(item.spelling);
                  setGloss(item.gloss);
                  setArabic(item.arabic_script || "");
                  setError("");
                }}
                onCancel={() => setEditing(null)}
                onSave={() => {
                  updateItem(api, item.id, spelling, gloss, language === "arabic" ? arabic : undefined)
                    .then((saved) => {
                      setEditing(null);
                      patchWord(item.id, saved.spelling || spelling, saved.gloss || gloss);
                      touchLibrary();
                    })
                    .catch((err: Error) => setError(err.message));
                }}
              />
            ))}
          </View>
        ))}
      </BodyScroll>
    </Screen>
  );
}

function WordRow({
  item,
  editing,
  spelling,
  gloss,
  arabic,
  arabicFirst,
  onArabic,
  onSpelling,
  onGloss,
  onEdit,
  onForms,
  onCancel,
  onSave,
}: {
  item: NotebookItem;
  editing: boolean;
  spelling: string;
  gloss: string;
  arabic: string;
  arabicFirst: boolean;
  onArabic: (value: string) => void;
  onSpelling: (value: string) => void;
  onGloss: (value: string) => void;
  onEdit: () => void;
  onForms: () => void;
  onCancel: () => void;
  onSave: () => void;
}) {
  const theme = useTheme();
  const { language } = useSession();
  if (editing) {
    return (
      <View style={{ gap: 8, paddingVertical: 8 }}>
        <TextInput
          value={spelling}
          onChangeText={onSpelling}
          autoCapitalize="none"
          autoCorrect={false}
          returnKeyType="done"
          onSubmitEditing={onSave}
          accessibilityLabel={copy(language, "colArabizi")}
          style={{ minHeight: 40, color: theme.label, borderWidth: 1, borderColor: theme.separator, borderRadius: 8, paddingHorizontal: 10, backgroundColor: theme.field }}
        />
        <TextInput
          value={gloss}
          onChangeText={onGloss}
          returnKeyType="done"
          onSubmitEditing={onSave}
          accessibilityLabel={copy(language, "colGloss")}
          style={{ minHeight: 40, color: theme.label, borderWidth: 1, borderColor: theme.separator, borderRadius: 8, paddingHorizontal: 10, backgroundColor: theme.field }}
        />
        {language === "arabic" ? <TextInput value={arabic} onChangeText={onArabic} accessibilityLabel="Arabic spelling" placeholder="Arabic spelling" placeholderTextColor={theme.tertiary} style={{ minHeight: 40, color: theme.label, borderWidth: 1, borderColor: theme.separator, borderRadius: 8, paddingHorizontal: 10, writingDirection: "rtl", textAlign: "right" }} /> : null}
        <View style={{ flexDirection: "row", gap: 8 }}>
          <Button label={UI.save} onPress={onSave} />
          <Button kind="text" label={UI.cancel} onPress={onCancel} />
        </View>
      </View>
    );
  }
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: theme.separator }}>
      <View style={{ flex: 1 }}>
        <Text style={{ fontFamily: theme.reading, fontSize: 20, color: theme.label, writingDirection: arabicFirst ? "rtl" : "auto", textAlign: arabicFirst ? "right" : "auto" }}>{arabicFirst ? item.arabic_script || "—" : item.spelling}</Text>
        {arabicFirst ? <Text style={{ color: theme.secondary }}>{item.spelling} · {item.arabic_source === "arwords" ? "Arwords" : item.arabic_source === "user" ? "Your edit" : item.arabic_source === "ai" ? "AI suggestion — review" : item.arabic_source === "dictionary" ? "Wiktionary" : "No spelling yet"}</Text> : null}
        <Text style={{ color: theme.secondary, marginTop: 2 }}>{item.gloss}</Text>
      </View>
      <Text style={{ color: theme.secondary, fontSize: 12 }}>{item.kind}</Text>
      {language === "arabic" ? <Pressable onPress={onForms} hitSlop={8}><Text style={{ color: theme.blueText }}>Forms</Text></Pressable> : null}
      <Pressable onPress={onEdit} hitSlop={8}>
        <Text style={{ color: theme.blueText, fontWeight: "600" }}>{UI.edit}</Text>
      </Pressable>
    </View>
  );
}
