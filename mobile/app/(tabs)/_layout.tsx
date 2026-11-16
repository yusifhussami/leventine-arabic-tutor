import { NativeTabs } from "expo-router/unstable-native-tabs";
import * as Haptics from "expo-haptics";

import { useTheme } from "@/src/theme";

export const unstable_settings = {
  initialRouteName: "learn",
};

export default function TabLayout() {
  const theme = useTheme();
  return (
    <NativeTabs
      tintColor={theme.blue}
      iconColor={{ default: theme.secondary, selected: theme.blue }}
      blurEffect="systemChromeMaterial"
      labelStyle={{
        default: { color: theme.secondary, fontSize: 10 },
        selected: { color: theme.blue, fontSize: 10 },
      }}
      screenListeners={{
        tabPress: () => {
          void Haptics.selectionAsync();
        },
      }}
    >
      <NativeTabs.Trigger name="learn" disableAutomaticContentInsets>
        <NativeTabs.Trigger.Icon sf="pencil.and.outline" md="edit_note" />
        <NativeTabs.Trigger.Label>Learn</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="index" disableAutomaticContentInsets>
        <NativeTabs.Trigger.Icon sf="calendar" md="calendar_today" />
        <NativeTabs.Trigger.Label>Today</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="practice" hidden />
      <NativeTabs.Trigger name="words" disableAutomaticContentInsets>
        <NativeTabs.Trigger.Icon sf="book" md="menu_book" />
        <NativeTabs.Trigger.Label>Words</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
      <NativeTabs.Trigger name="checklist" hidden />
      <NativeTabs.Trigger name="settings" disableAutomaticContentInsets>
        <NativeTabs.Trigger.Icon sf="gearshape" md="settings" />
        <NativeTabs.Trigger.Label>Settings</NativeTabs.Trigger.Label>
      </NativeTabs.Trigger>
    </NativeTabs>
  );
}
