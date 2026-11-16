import type { ConfigContext, ExpoConfig } from "expo/config";

const microphonePermission =
  "Sawt uses the microphone so you can talk with your tutor during practice.";
const speechPermission =
  "Sawt uses speech recognition to turn what you say into text during practice.";

export default ({ config }: ConfigContext): ExpoConfig => ({
  ...config,
  name: "Sawt",
  slug: "sawt",
  version: "1.0.0",
  orientation: "portrait",
  icon: "./assets/images/icon.png",
  scheme: "sawt",
  userInterfaceStyle: "automatic",
  ios: {
    supportsTablet: true,
    bundleIdentifier: "com.sawt.tutor",
    buildNumber: "1",
    config: {
      usesNonExemptEncryption: false,
    },
    infoPlist: {
      NSMicrophoneUsageDescription: microphonePermission,
      NSSpeechRecognitionUsageDescription: speechPermission,
      ITSAppUsesNonExemptEncryption: false,
    },
  },
  android: {
    package: "com.sawt.tutor",
    adaptiveIcon: {
      backgroundColor: "#F2F2F7",
      foregroundImage: "./assets/images/android-icon-foreground.png",
      backgroundImage: "./assets/images/android-icon-background.png",
      monochromeImage: "./assets/images/android-icon-monochrome.png",
    },
    permissions: ["RECORD_AUDIO"],
  },
  web: {
    bundler: "metro",
    output: "static",
    favicon: "./assets/images/favicon.png",
  },
  plugins: [
    "expo-router",
    [
      "expo-splash-screen",
      {
        image: "./assets/images/splash-icon.png",
        resizeMode: "contain",
        backgroundColor: "#f2f2f7",
      },
    ],
    "expo-secure-store",
    "@clerk/expo",
    [
      "expo-audio",
      {
        microphonePermission,
      },
    ],
    [
      "expo-speech-recognition",
      {
        microphonePermission,
        speechRecognitionPermission: speechPermission,
        androidSpeechServicePackages: ["com.google.android.googlequicksearchbox"],
      },
    ],
    "@react-native-community/datetimepicker",
  ],
  experiments: {
    typedRoutes: true,
  },
  extra: {
    supportsRtl: false,
  },
});
