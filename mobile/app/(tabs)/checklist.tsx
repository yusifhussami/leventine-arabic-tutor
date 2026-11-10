import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Haptics from "expo-haptics";
import { useEffect, useState } from "react";
import { Pressable, Text, TextInput, View } from "react-native";

import { BodyScroll, Screen } from "@/src/components/ui";
import { UI } from "@/src/copy";
import { checklistStorageKey, normalizeChecklist, randomId, sortChecklist } from "@/src/logic";
import { useSession } from "@/src/session";
import { useTheme } from "@/src/theme";
import type { ChecklistItem } from "@/src/types";

export default function ChecklistScreen() {
  const theme = useTheme();
  const { language } = useSession();
  const [items, setItems] = useState<ChecklistItem[]>([]);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    let cancelled = false;
    AsyncStorage.getItem(checklistStorageKey(language)).then((raw) => {
      if (cancelled) return;
      try {
        setItems(normalizeChecklist(raw ? JSON.parse(raw) : []));
      } catch {
        setItems([]);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [language]);

  const save = (next: ChecklistItem[]) => {
    setItems(next);
    void AsyncStorage.setItem(
      checklistStorageKey(language),
      JSON.stringify(next.map(({ id, title, description, done, open }) => ({ id, title, description, done, open }))),
    );
  };

  const openItems = items.filter((item) => !item.done);
  const doneItems = items.filter((item) => item.done);

  return (
    <Screen title={UI.tabChecklist} background="grouped">
      <BodyScroll>
        <Text style={{ color: theme.label, fontSize: 28, fontWeight: "600" }}>{UI.tabChecklist}</Text>
        <Text style={{ color: theme.secondary, fontSize: 15, lineHeight: 21 }}>{UI.checklistHint}</Text>
        <View style={{ backgroundColor: theme.window, borderRadius: 12, overflow: "hidden" }}>
          {openItems.map((item) => (
            <ChecklistRow key={item.id} item={item} onChange={(next) => save(next.done === item.done ? items.map((row) => (row.id === item.id ? next : row)) : sortChecklist(items.map((row) => (row.id === item.id ? next : row))))} onDelete={() => save(items.filter((row) => row.id !== item.id))} />
          ))}
        </View>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 10, backgroundColor: theme.window, borderRadius: 12, paddingHorizontal: 14, minHeight: 52 }}>
          <Text style={{ color: theme.blue, fontSize: 22, fontWeight: "500" }}>+</Text>
          <TextInput
            value={draft}
            onChangeText={setDraft}
            placeholder={UI.checklistNew}
            placeholderTextColor={theme.tertiary}
            style={{ flex: 1, color: theme.label, fontSize: 17, minHeight: 44 }}
            onSubmitEditing={() => {
              const title = draft.trim();
              if (!title) return;
              save([...items, { id: randomId(), title, description: "", done: false, open: false }]);
              setDraft("");
            }}
            returnKeyType="done"
          />
        </View>
        {items.length === 0 ? <Text style={{ color: theme.secondary }}>{UI.checklistEmpty}</Text> : null}
        {doneItems.length > 0 ? (
          <View style={{ gap: 8 }}>
            <Text style={{ color: theme.secondary, fontWeight: "600" }}>{UI.checklistDone}</Text>
            <View style={{ backgroundColor: theme.window, borderRadius: 12, overflow: "hidden" }}>
              {doneItems.map((item) => (
                <ChecklistRow key={item.id} item={item} onChange={(next) => save(sortChecklist(items.map((row) => (row.id === item.id ? next : row))))} onDelete={() => save(items.filter((row) => row.id !== item.id))} />
              ))}
            </View>
          </View>
        ) : null}
      </BodyScroll>
    </Screen>
  );
}

function ChecklistRow({
  item,
  onChange,
  onDelete,
}: {
  item: ChecklistItem;
  onChange: (item: ChecklistItem) => void;
  onDelete: () => void;
}) {
  const theme = useTheme();
  return (
    <View style={{ borderBottomWidth: 1, borderBottomColor: theme.separator }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 12, minHeight: 52, paddingHorizontal: 14 }}>
        <Pressable
          accessibilityRole="checkbox"
          accessibilityState={{ checked: item.done }}
          accessibilityLabel={item.done ? "Move back to checklist" : "Move to Done"}
          onPress={() => {
            void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
            onChange({ ...item, done: !item.done, open: false });
          }}
          style={{ width: 28, height: 28, borderRadius: 14, borderWidth: item.done ? 0 : 1.7, borderColor: theme.tertiary, backgroundColor: item.done ? theme.switchOn : "transparent", alignItems: "center", justifyContent: "center" }}
        >
          {item.done ? <Text style={{ color: "#ffffff", fontWeight: "700" }}>✓</Text> : null}
        </Pressable>
        <TextInput
          value={item.title}
          onChangeText={(title) => onChange({ ...item, title })}
          onEndEditing={(event) => {
            const title = event.nativeEvent.text.trim();
            if (!title && !item.description) onDelete();
            else onChange({ ...item, title });
          }}
          returnKeyType="done"
          blurOnSubmit
          style={{
            flex: 1,
            color: item.done ? theme.secondary : theme.label,
            fontSize: 17,
            minHeight: 44,
          }}
        />
        <Pressable
          accessibilityLabel={UI.checklistNote}
          accessibilityState={{ expanded: item.open }}
          onPress={() => onChange({ ...item, open: !item.open })}
          hitSlop={8}
        >
          <Text style={{ color: item.open ? theme.blue : theme.tertiary, fontSize: 18 }}>{item.open ? "⌄" : "›"}</Text>
        </Pressable>
      </View>
      {item.open ? (
        <View style={{ paddingLeft: 54, paddingRight: 14, paddingBottom: 12, gap: 8 }}>
          <TextInput
            value={item.description}
            onChangeText={(description) => onChange({ ...item, description })}
            onEndEditing={(event) => onChange({ ...item, description: event.nativeEvent.text.trim() })}
            placeholder={UI.checklistNote}
            placeholderTextColor={theme.tertiary}
            autoFocus
            multiline
            style={{ minHeight: 72, color: theme.label, backgroundColor: theme.grouped, borderRadius: 10, padding: 10, fontSize: 16 }}
          />
          <Pressable onPress={onDelete} style={{ alignSelf: "flex-end" }}>
            <Text style={{ color: theme.red, fontWeight: "500" }}>{UI.checklistDelete}</Text>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}
