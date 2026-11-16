import DateTimePicker from "@react-native-community/datetimepicker";
import * as DocumentPicker from "expo-document-picker";
import { File } from "expo-file-system";
import { router } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { Platform, Pressable, StyleSheet, Text, View } from "react-native";

import { importCsv, loadItems, loadNextLesson, previewLesson, saveCalendar, saveLesson } from "@/src/api";
import { BodyScroll, Button, ErrorText, Field, Hint, Screen } from "@/src/components/ui";
import { UI, copy, importDone } from "@/src/copy";
import { formatDay, formatLesson, isoDay, recentLessons } from "@/src/logic";
import { usePractice } from "@/src/practice";
import { useSession } from "@/src/session";
import { useTheme } from "@/src/theme";
import type { NotebookItem, PreviewItem } from "@/src/types";

export default function TodayScreen() {
  const theme = useTheme();
  const { api, language, touchLibrary } = useSession();
  const { openWord } = usePractice();
  const [day, setDay] = useState(() => new Date());
  const [showDate, setShowDate] = useState(false);
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<PreviewItem[]>([]);
  const [error, setError] = useState("");
  const [note, setNote] = useState(false);
  const [recent, setRecent] = useState<NotebookItem[][]>([]);
  const [csvName, setCsvName] = useState("");
  const [csvText, setCsvText] = useState("");
  const [importError, setImportError] = useState("");
  const [importNote, setImportNote] = useState(false);
  const [lesson, setLesson] = useState("");
  const [lessonSummary, setLessonSummary] = useState("");
  const [calendarOpen, setCalendarOpen] = useState(true);
  const [calendarUrl, setCalendarUrl] = useState("");
  const [calendarError, setCalendarError] = useState("");
  const [busy, setBusy] = useState(false);

  const refreshRecent = useCallback(async () => {
    const items = await loadItems(api);
    setRecent(Array.isArray(items) ? recentLessons(items) : []);
  }, [api]);

  const refreshLesson = useCallback(async () => {
    try {
      const payload = await loadNextLesson(api);
      setCalendarOpen(!payload.connected);
      if (!payload.connected) {
        setLesson(UI.connectCalendar);
        setLessonSummary("");
        return;
      }
      if (!payload.lesson) {
        setLesson(UI.noLesson);
        setLessonSummary("");
        return;
      }
      setLesson(formatLesson(payload.lesson.start));
      setLessonSummary(payload.lesson.summary || "");
    } catch (err) {
      setLesson(err instanceof Error ? err.message : UI.calendarReadError);
      setLessonSummary("");
    }
  }, [api]);

  useEffect(() => {
    setLesson(UI.lookingUpLesson);
    refreshLesson().catch(() => setLesson(UI.calendarReadError));
    refreshRecent().catch(() => setRecent([]));
  }, [refreshLesson, refreshRecent, language]);

  const openSavedWord = (item: NotebookItem) => {
    openWord(item);
    router.navigate("/practice");
  };

  return (
    <Screen title={UI.tabToday}>
      <BodyScroll>
        <Text style={{ color: theme.label, fontSize: 28, fontWeight: "600" }}>{UI.addLesson}</Text>
        <Hint>{copy(language, "lessonHint")}</Hint>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Text style={{ color: theme.secondary, fontWeight: "600" }}>{UI.lessonDate}</Text>
          {Platform.OS === "ios" ? (
            <DateTimePicker
              value={day}
              mode="date"
              display="compact"
              themeVariant={theme.scheme}
              onChange={(_, selected) => {
                if (selected) setDay(selected);
              }}
            />
          ) : (
            <Pressable onPress={() => setShowDate(true)}>
              <Text style={{ color: theme.blueText, fontSize: 16 }}>{isoDay(day)}</Text>
            </Pressable>
          )}
        </View>
        {showDate && Platform.OS !== "ios" ? (
          <DateTimePicker
            value={day}
            mode="date"
            onChange={(_, selected) => {
              setShowDate(false);
              if (selected) setDay(selected);
            }}
          />
        ) : null}
        <Field
          label={UI.wordsLabel}
          multiline
          value={text}
          onChangeText={setText}
          placeholder={copy(language, "pastePlaceholder")}
        />
        <View style={{ flexDirection: "row", gap: 8 }}>
          <Button
            label={UI.preview}
            onPress={() => {
              setError("");
              setNote(false);
              previewLesson(api, text)
                .then((items) => setPreview(Array.isArray(items) ? items : []))
                .catch((err: Error) => setError(err.message));
            }}
          />
          <Button
            kind="secondary"
            label={UI.saveLesson}
            disabled={busy}
            onPress={() => {
              setBusy(true);
              setError("");
              setNote(false);
              saveLesson(api, isoDay(day), text)
                .then(async (saved) => {
                  setText("");
                  setPreview([]);
                  if (saved.skipped && saved.skipped.length) {
                    setNote(true);
                    setError(`Already saved: ${saved.skipped.map((item) => item.spelling).join(", ")}`);
                  }
                  touchLibrary();
                  await refreshRecent();
                  router.navigate("/words");
                })
                .catch((err: Error) => {
                  setNote(false);
                  setError(err.message);
                })
                .finally(() => setBusy(false));
            }}
          />
        </View>
        <ErrorText note={note}>{error}</ErrorText>
        {preview.length > 0 ? (
          <View>
            <View style={{ flexDirection: "row", paddingVertical: 8 }}>
              <Text style={{ flex: 1, color: theme.secondary, fontSize: 12, fontWeight: "600" }}>
                {copy(language, "colArabizi")}
              </Text>
              <Text style={{ flex: 1, color: theme.secondary, fontSize: 12, fontWeight: "600" }}>
                {copy(language, "colGloss")}
              </Text>
            </View>
            {preview.map((item) => (
              <View
                key={`${item.spelling}-${item.gloss}`}
                style={{ flexDirection: "row", gap: 8, paddingVertical: 8, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: theme.separator }}
              >
                <Text style={{ flex: 1, fontFamily: theme.reading, fontSize: 18, color: theme.label }}>{item.spelling}</Text>
                <Text style={{ flex: 1, color: theme.label, fontSize: 16 }}>{item.gloss}</Text>
                <Text style={{ color: theme.secondary, fontSize: 12 }}>{item.kind}</Text>
              </View>
            ))}
          </View>
        ) : null}

        {recent.length > 0 ? (
          <View style={{ gap: 8, marginTop: 12 }}>
            <Text style={{ color: theme.label, fontSize: 22, fontWeight: "600" }}>{UI.recent}</Text>
            {recent.map((rows) => (
              <View key={rows[0].lesson_id} style={{ gap: 4 }}>
                <Text style={{ color: theme.secondary, fontWeight: "600", fontSize: 13 }}>{formatDay(rows[0].learned_on)}</Text>
                {rows.map((item) => (
                  <Pressable key={item.id} onPress={() => openSavedWord(item)} style={{ paddingVertical: 6, flexDirection: "row", alignItems: "center", gap: 8 }}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontFamily: theme.reading, fontSize: 18, color: theme.label }}>{item.spelling}</Text>
                      <Text style={{ color: theme.secondary }}>{item.gloss}</Text>
                    </View>
                    <Text style={{ color: theme.secondary, fontSize: 12 }}>{item.kind}</Text>
                  </Pressable>
                ))}
              </View>
            ))}
          </View>
        ) : null}

        <View style={{ gap: 8, marginTop: 12, paddingTop: 16, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: theme.separator }}>
          <Text style={{ color: theme.label, fontSize: 22, fontWeight: "600" }}>{UI.importCsv}</Text>
          <Hint>{copy(language, "importHint")}</Hint>
          <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap" }}>
            <Button
              kind="secondary"
              label={UI.chooseCsv}
              onPress={() => {
                setImportError("");
                DocumentPicker.getDocumentAsync({
                  type: ["text/csv", "text/comma-separated-values", "public.comma-separated-values-text", "*/*"],
                  copyToCacheDirectory: true,
                })
                  .then(async (result) => {
                    if (result.canceled || !result.assets?.[0]) {
                      setCsvName("");
                      setCsvText("");
                      return;
                    }
                    const asset = result.assets[0];
                    const file = new File(asset.uri);
                    const contents = await file.text();
                    setCsvName(asset.name || "sheet.csv");
                    setCsvText(contents);
                  })
                  .catch((err: Error) => setImportError(err.message));
              }}
            />
            <Button
              kind="tint"
              label={UI.importWords}
              disabled={!csvText.trim() || busy}
              onPress={() => {
                setBusy(true);
                setImportError("");
                setImportNote(false);
                importCsv(api, csvText, isoDay(day), language)
                  .then(async (saved) => {
                    setCsvName("");
                    setCsvText("");
                    setImportNote(true);
                    setImportError(importDone(saved.days, saved.items));
                    touchLibrary();
                    await refreshRecent();
                    router.navigate("/words");
                  })
                  .catch((err: Error) => {
                    setImportNote(false);
                    setImportError(err.message);
                  })
                  .finally(() => setBusy(false));
              }}
            />
          </View>
          <Text style={{ color: theme.secondary }}>{csvName || UI.noCsvChosen}</Text>
          <ErrorText note={importNote}>{importError}</ErrorText>
        </View>

        <View style={{ gap: 8, padding: 16, borderRadius: 12, backgroundColor: theme.grouped }}>
          <Text style={{ color: theme.secondary, fontSize: 12, fontWeight: "600" }}>{UI.nextLesson}</Text>
          <Text style={{ fontFamily: theme.reading, fontSize: 22, color: theme.label }}>{lesson}</Text>
          {lessonSummary ? <Text style={{ color: theme.secondary }}>{lessonSummary}</Text> : null}
          {calendarOpen ? (
            <View style={{ gap: 8, marginTop: 8 }}>
              <Text style={{ color: theme.label, fontSize: 20, fontWeight: "600" }}>{UI.calendar}</Text>
              <Hint>{UI.calendarHint}</Hint>
              <Field
                label={UI.icalLink}
                value={calendarUrl}
                onChangeText={setCalendarUrl}
                autoCapitalize="none"
                autoCorrect={false}
                placeholder="https://calendar.google.com/calendar/ical/..."
              />
              <Button
                kind="tint"
                label={UI.saveCalendar}
                onPress={() => {
                  setCalendarError("");
                  saveCalendar(api, calendarUrl)
                    .then(async () => {
                      setCalendarUrl("");
                      await refreshLesson();
                    })
                    .catch((err: Error) => setCalendarError(err.message));
                }}
              />
              <ErrorText>{calendarError}</ErrorText>
            </View>
          ) : null}
        </View>
      </BodyScroll>
    </Screen>
  );
}
