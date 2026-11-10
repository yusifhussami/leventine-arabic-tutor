import { createAudioPlayer, setAudioModeAsync, type AudioPlayer } from "expo-audio";
import { File, Paths } from "expo-file-system";

let player: AudioPlayer | null = null;
let currentFile: File | null = null;
let modeReady = false;

async function ensureMode() {
  if (modeReady) return;
  await setAudioModeAsync({
    playsInSilentMode: true,
    allowsRecording: false,
    interruptionMode: "doNotMix",
  });
  modeReady = true;
}

export async function playWavBytes(bytes: Uint8Array): Promise<void> {
  await ensureMode();
  stopPlayback();
  const file = new File(Paths.cache, `sawt-${Date.now()}.wav`);
  file.create();
  file.write(bytes);
  currentFile = file;
  const next = createAudioPlayer({ uri: file.uri });
  player = next;
  await new Promise<void>((resolve, reject) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(safety);
      subscription.remove();
      resolve();
    };
    const subscription = next.addListener("playbackStatusUpdate", (status) => {
      if (status.didJustFinish) finish();
      else if (
        status.isLoaded &&
        !status.playing &&
        status.duration > 0 &&
        status.currentTime >= status.duration - 0.08
      ) {
        finish();
      }
    });
    const safety = setTimeout(finish, 45000);
    try {
      next.play();
    } catch (error) {
      settled = true;
      clearTimeout(safety);
      subscription.remove();
      reject(error);
    }
  });
}

export function stopPlayback(): void {
  try {
    player?.pause();
    player?.remove();
  } catch {
    // Already released.
  }
  player = null;
  try {
    if (currentFile?.exists) currentFile.delete();
  } catch {
    // Cache cleanup is best-effort.
  }
  currentFile = null;
}
