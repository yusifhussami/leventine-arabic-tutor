# Sawt for iPhone

This is the native iPhone app for Sawt. It is the same notebook as the website: Today, Practice, Words, Checklist, and Settings. It calls the existing Vercel (or local) API. It does not add server routes, so the Vercel Hobby function limit is unchanged.

The interface follows the website’s colors, type, and wording, and uses iPhone conventions: a native tab bar, safe areas, haptics, the system keyboard, and light or dark mode from the system setting.

## What you need

| Path | Cost | Mac | Microphone practice |
| --- | --- | --- | --- |
| Expo Go | Free | No | Typing works. The speech recognizer does not run inside Expo Go. |
| Xcode + free Apple ID | Free. The install expires after 7 days and must be rebuilt. | Yes | Yes |
| EAS internal install (preview or development) | Apple Developer Program, $99/year. Expo’s free plan includes a limited number of cloud builds. | No | Yes |
| **TestFlight (the install to use)** | Apple Developer Program, $99/year. No paid Expo plan is required to start. | No | Yes |

A free Apple ID can sideload from Xcode for 7 days. TestFlight, Ad Hoc, and a lasting install need the paid [Apple Developer Program](https://developer.apple.com/programs/).

## 1. Point the app at your server

From `mobile/`:

```bash
cp .env.example .env
```

Set `EXPO_PUBLIC_API_URL` to the Vercel origin, with no path and no trailing slash:

```bash
EXPO_PUBLIC_API_URL=https://your-project.vercel.app
```

You can skip the file and type that address on the first screen. It is saved on the phone. Settings → Server changes it later.

The Clerk publishable key is read from `GET /api/config` on that server, the same key the website uses. Set `EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY` only to override that response.

Before the first device build, turn on Clerk’s **Native API** (Clerk Dashboard → Native applications) and add the iOS bundle id `com.sawt.tutor`. Hosted sign-in uses the same Clerk application as the website. The session token is sent as `Authorization: Bearer`, which the Python API already checks.

## 2. Expo Go (quick look, no Apple install)

```bash
cd mobile
npm install
npx expo start
```

Install **Expo Go** from the App Store. Scan the QR code in the terminal (iPhone Camera app, or Expo Go’s scanner). Phone and computer must be on the same network. If the CLI is set to a development build, press `s` to switch the QR code to Expo Go.

Sign in with the same account as the website. Paste a lesson, search words, edit, import a CSV, use Checklist, switch Arabic/Japanese, and type a practice line. Tapping the circle in Expo Go asks you to type, because Expo Go cannot load the speech-recognition native module. Playback of Sawt’s voice still uses the server when a typed turn returns audio.

## 3. TestFlight (install on your iPhone)

No Mac. EAS builds in the cloud and submits the binary to App Store Connect.

1. Enroll in the [Apple Developer Program](https://developer.apple.com/programs/) ($99/year). Wait until the membership is active.
2. Create a free [Expo](https://expo.dev) account.
3. In App Store Connect, create the app if it does not exist yet:
   - Apps → New App → iOS
   - Name: **Sawt**
   - Bundle ID: `com.sawt.tutor` (register that identifier under Certificates, Identifiers & Profiles if it is not listed; the first `eas build` can also create it)
   - SKU: `sawt`
4. From `mobile/`:

```bash
npm install
npx eas-cli login
npx eas-cli init
```

`eas init` links this folder to an Expo project. The slug in `app.config.ts` is `sawt`.

5. Put the server address where the cloud build can see it. Either export it in the shell before building, or save it on Expo:

```bash
npx eas-cli env:create --name EXPO_PUBLIC_API_URL --value https://your-project.vercel.app --environment production --visibility plaintext
```

The publishable key is not a secret. The API URL is not a secret either. Do not put `OPENROUTER_API_KEY` or `DATABASE_URL` in the app.

6. Build the store binary. The production profile in `eas.json` uses store distribution and increments the iOS build number on Expo’s servers (`cli.appVersionSource` is `remote`, `autoIncrement` is true). The marketing version is `version` in `app.config.ts` (`1.0.0`). Bump that when you want a new version name; build numbers increment by themselves.

```bash
npx eas-cli build -p ios --profile production
```

The first run asks you to sign in with your Apple ID and creates the distribution certificate and provisioning profile. You can also use an App Store Connect API key. Answer yes to the encryption question if it appears; the app only uses HTTPS, and `ios.config.usesNonExemptEncryption` is already `false` so TestFlight should not sit on Missing Compliance.

7. Submit that build:

```bash
npx eas-cli submit -p ios --profile production --latest
```

8. In App Store Connect, open the Sawt app → TestFlight. Processing often takes a few minutes. Under **Internal Testing**, add yourself. Internal testers are App Store Connect users on the team (Admin, Developer, App Manager, or Marketing). If you are the account holder, you are already eligible: add the build to the internal group.
9. On the iPhone, install **TestFlight** from the App Store, accept the build, and install Sawt. The microphone and speech-recognition prompts appear the first time you tap the practice circle.

Later builds:

```bash
npx eas-cli build -p ios --profile production --auto-submit
```

## 4. Other ways to install

### EAS development or preview link (no Mac, paid Apple Developer)

`preview` is an internal/ad hoc install you open from an EAS link or QR code. `development` is the same kind of install plus the Expo dev client, so `npx expo start` can reload JavaScript on the phone. Both need the paid developer account so Apple can sign the binary for your device. Register the iPhone when EAS asks (it shows a URL to install a provisioning profile).

```bash
npx eas-cli build -p ios --profile preview
npx eas-cli build -p ios --profile development
```

Open the build page on the iPhone and install. These builds are not TestFlight. They are the direct sideload path when you do not want to wait for App Store Connect processing. Microphone practice works.

### Xcode and a free Apple ID (Mac required)

This is the free personal install. It expires after 7 days. You need a Mac, Xcode, and a cable or the same Wi‑Fi for the device.

```bash
cd mobile
npm install
npx expo prebuild -p ios
open ios/Sawt.xcworkspace
```

In Xcode: Signing & Capabilities → Team → your personal Apple ID. Select the iPhone and press Run. Trust the developer under Settings → General → VPN & Device Management if iOS asks. After 7 days, Run again from Xcode to re-sign. A free team can only have a few apps installed this way. TestFlight is the path that does not expire every week.

`ios/` is generated and gitignored. Change the bundle id in `app.config.ts` before the first signing if `com.sawt.tutor` is not the id you registered.

## Permissions

`app.config.ts` sets the strings iOS shows:

- Microphone: practice conversations
- Speech recognition: turning what you say into text

Sawt does not request them until you tap the circle or a situation (Coffee, Restaurant, Shop, Taxi). Replies are audio from `POST /api/talk` (WAV), with `POST /api/speak` as the fallback. The microphone hears you; the server still writes the reply and the voice, the same loop as the website.

## Scripts

```bash
npm run typecheck
npm test
npm start
```

## Design decisions

- **Expo SDK 57 and React Native**, TypeScript, Expo Router, and the native tab bar (`expo-router/unstable-native-tabs`). Five tabs match the website: Today, Practice, Words, Checklist, Settings. A sidebar does not fit an iPhone; the sections are the same.
- **Same API.** No new Vercel functions. `mobile/` is excluded from the Python function bundle in `vercel.json`.
- **Clerk hosted Account Portal** (`@clerk/expo`) so sign-in uses whatever methods the website’s Clerk app already allows. The token is stored with `expo-secure-store`.
- **Speech:** `expo-speech-recognition` (iOS `SFSpeechRecognizer`, `ar-SA` or `ja-JP`). A final phrase sends after about 0.7s of quiet; interim speech waits about 1.1s. After Sawt’s WAV plays, the mic starts again following a 300ms gap. Expo Go does not include this native module, so that build types instead.
- **Checklist** stays on the phone, one list per learning language (`checklist:arabic` / `checklist:japanese`), same as the website’s `localStorage`. It is not copied to the server, so the phone list and the browser list are separate.
- **Server address** is the one extra control. The website is already on the API origin; the app has to be told where that origin is.
- Colors, English UI copy, Arabizi/kana-first rows, situation chips, and the صوت / 音 mark follow the website. Touch targets are larger than the desktop stylesheet. Georgia stands in for the website’s serif on iOS. The practice orb is the same blue circle, drawn natively, and it reacts while you are listening.

## Feature parity

| Feature | Status | Notes |
| --- | --- | --- |
| Today: paste a lesson, preview, save, lesson date | Done | Same `/api/preview` and `/api/lessons`. Saving opens Words. |
| Today: CSV import | Done | Files picker. Same `/api/import-csv`, including Japanese kanji/kana sheets. |
| Today: recent lessons | Done | Latest three lessons, with kind, tap a word to practice. |
| Today: next lesson and private iCal link | Done | Same `/api/next-lesson` and `/api/calendar`. The link is not shown again after it is saved. |
| Words: list grouped by lesson day, Arabizi or kana first, kind | Done | |
| Words: edit spelling and meaning | Done | `PUT /api/items/:id`. An open practice card updates with the edit. |
| Words: semantic search | Done | Same `GET /api/items?q=`. Short queries and ranking stay on the server. Results stay in relevance order under “Best matches”. |
| Practice: voice call | Done on a dev build, TestFlight, or Xcode install. Partial in Expo Go | Same `/api/talk` NDJSON loop, situations, corrections, and “type a line”. Expo Go has no on-device recognizer. |
| Practice: Sawt’s voice | Done | Server WAV via `expo-audio`, including the silent switch. |
| Practice: write one sentence for a saved word, similar words | Done | Same `/api/practice` and `/api/items/:id/similar`. |
| Checklist | Done | Add, rename, note, delete, tick into Done, untick back. Per learning language, on this device. |
| Settings: Levantine Arabic or Japanese | Done | `POST /api/settings`. Mic, TTS, copy, and the word list follow it. UI stays English. Brand flips between صوت and 音. |
| Settings: account | Done, with a native sign-out | Sign-in is Clerk’s hosted Account Portal. Manage account opens the Clerk profile URL when Clerk returns one. Sign out ends the session on the phone (the website hides sign-out inside Clerk’s modal). |
| Sign-in required on the hosted server | Done | Local `lexicon.serve` still works with no account, matching the website. |
| Light and dark mode | Done | Follows the system, same palette as the website. |
| Delete a word, sync checklist to the account, in-app appearance toggle | Not on the website | Not added here. |

## Limits

- This environment cannot install the app on a physical iPhone or run the iOS simulator. Typecheck and the logic tests pass. The phone install is the step above.
- Expo Go will not prompt for the microphone. Use TestFlight, an EAS internal build, or Xcode for that.
- Clerk Native API must be enabled or hosted sign-in will fail.
- The first TestFlight build needs an active Apple Developer membership. Internal testing does not require a public App Store review.
- Checklist items do not move between the website and the phone.
