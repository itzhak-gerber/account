import createCache from "@emotion/cache";
import { CacheProvider } from "@emotion/react";
import CssBaseline from "@mui/material/CssBaseline";
import GlobalStyles from "@mui/material/GlobalStyles";
import { ThemeProvider } from "@mui/material/styles";
import useMediaQuery from "@mui/material/useMediaQuery";
import { type ReactNode, useEffect, useMemo } from "react";
import { prefixer } from "stylis";
import rtlPlugin from "stylis-plugin-rtl";

import { useMeQuery } from "../auth/useMe";
import { ROOT_FONT_SIZE, cacheDisplay, cachedDisplay } from "./display";
import { STATUS_BAR, createAppTheme } from "./theme";

// Emotion cache that flips left/right CSS for right-to-left Hebrew layout.
const rtlCache = createCache({ key: "muirtl", stylisPlugins: [prefixer, rtlPlugin] });

// iPhone and iPad: web pages ignore the system text size unless they ask for it. This font
// carries the size chosen in the device's settings (Dynamic Type).
const DEVICE_TEXT_SIZE = {
  "@supports (-webkit-touch-callout: none) and (font: -apple-system-body)": {
    html: { font: "-apple-system-body" },
  },
};

export function RtlThemeProvider({ children }: { children: ReactNode }) {
  const { data: me } = useMeQuery();
  const user = me?.user;
  const preferences = useMemo(
    () => (user ? { theme: user.theme, text_size: user.text_size } : cachedDisplay()),
    [user],
  );
  useEffect(() => {
    if (user) cacheDisplay(preferences);
  }, [user, preferences]);

  const deviceDark = useMediaQuery("(prefers-color-scheme: dark)", { noSsr: true });
  const mode = preferences.theme === "system" ? (deviceDark ? "dark" : "light") : preferences.theme;
  const theme = useMemo(() => createAppTheme(mode), [mode]);

  useEffect(() => {
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", STATUS_BAR[mode]);
  }, [mode]);

  const fontSize = ROOT_FONT_SIZE[preferences.text_size];
  return (
    <CacheProvider value={rtlCache}>
      <ThemeProvider theme={theme}>
        <CssBaseline enableColorScheme />
        <GlobalStyles styles={fontSize ? { html: { fontSize } } : DEVICE_TEXT_SIZE} />
        {children}
      </ThemeProvider>
    </CacheProvider>
  );
}
