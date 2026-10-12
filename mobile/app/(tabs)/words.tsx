import { router } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { Pressable, Text, TextInput, View } from "react-native";

import { loadItems, updateItem } from "@/src/api";
import { BodyScroll, Button, ErrorText, Screen } from "@/src/components/ui";
import { UI, copy, wordCount } from "@/src/copy";
import { formatDay, groupByDate } from "@/src/logic";
import { usePractice } from "@/src/practice";
import { useSession } from "@/src/session";
import { useTheme } from "@/src/theme";
import type { NotebookItem } from "@/src/types";

export default function WordsScreen() {
  const theme = useTheme();
  const { api, language, revision, touchLibrary } = useSession();
  const { openWord, patchWord } = usePractice();
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<NotebookItem[]>([]);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [spelling, setSpelling] = useState("");
  const [gloss, setGloss] = useState("");
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

  const practiceWord = (item: NotebookItem) => {
    openWord(item);
    router.navigate("/practice");
  };

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
                onSpelling={setSpelling}
                onGloss={setGloss}
                onOpen={() => practiceWord(item)}
                onEdit={() => {
                  setEditing(item.id);
                  setSpelling(item.spelling);
                  setGloss(item.gloss);
                  setError("");
                }}
                onCancel={() => setEditing(null)}
                onSave={() => {
                  updateItem(api, item.id, spelling, gloss)
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
                onSpelling={setSpelling}
                onGloss={setGloss}
                onOpen={() => practiceWord(item)}
                onEdit={() => {
                  setEditing(item.id);
                  setSpelling(item.spelling);
                  setGloss(item.gloss);
                  setError("");
                }}
                onCancel={() => setEditing(null)}
                onSave={() => {
                  updateItem(api, item.id, spelling, gloss)
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
  onSpelling,
  onGloss,
  onOpen,
  onEdit,
  onCancel,
  onSave,
}: {
  item: NotebookItem;
  editing: boolean;
  spelling: string;
  gloss: string;
  onSpelling: (value: string) => void;
  onGloss: (value: string) => void;
  onOpen: () => void;
  onEdit: () => void;
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
        <View style={{ flexDirection: "row", gap: 8 }}>
          <Button label={UI.save} onPress={onSave} />
          <Button kind="text" label={UI.cancel} onPress={onCancel} />
        </View>
      </View>
    );
  }
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: theme.separator }}>
      <Pressable onPress={onOpen} style={{ flex: 1 }}>
        <Text style={{ fontFamily: theme.reading, fontSize: 20, color: theme.label }}>{item.spelling}</Text>
        <Text style={{ color: theme.secondary, marginTop: 2 }}>{item.gloss}</Text>
      </Pressable>
      <Text style={{ color: theme.secondary, fontSize: 12 }}>{item.kind}</Text>
      <Pressable onPress={onEdit} hitSlop={8}>
        <Text style={{ color: theme.blueText, fontWeight: "600" }}>{UI.edit}</Text>
      </Pressable>
    </View>
  );
}
