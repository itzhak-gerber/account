import type { TextSize, ThemePreference } from "../api/types";

export interface DisplayPreferences {
  theme: ThemePreference;
  text_size: TextSize;
}

export const DEFAULT_DISPLAY: DisplayPreferences = { theme: "system", text_size: "device" };

// The preferences live on the user's profile (so they follow them to every device). A copy in
// this browser lets the sign-in page and the first paint use them before the profile loads.
const STORAGE_KEY = "display-preferences";

const THEMES: readonly ThemePreference[] = ["system", "light", "dark"];
const SIZES: readonly TextSize[] = ["device", "large", "xlarge"];

export function cachedDisplay(): DisplayPreferences {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as Partial<
      Record<keyof DisplayPreferences, unknown>
    >;
    return {
      theme: THEMES.find((t) => t === raw.theme) ?? DEFAULT_DISPLAY.theme,
      text_size: SIZES.find((s) => s === raw.text_size) ?? DEFAULT_DISPLAY.text_size,
    };
  } catch {
    return DEFAULT_DISPLAY;
  }
}

export function cacheDisplay(preferences: DisplayPreferences): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
  } catch {
    // Storage blocked (private mode): the profile still holds the preferences.
  }
}

// Root font size: every size in the app is in rem, so this scales all text and controls.
// "device" leaves the browser's own size (which follows the phone or browser settings).
export const ROOT_FONT_SIZE: Record<TextSize, string | undefined> = {
  device: undefined,
  large: "112.5%",
  xlarge: "125%",
};
