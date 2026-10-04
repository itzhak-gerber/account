import createCache from "@emotion/cache";
import { CacheProvider } from "@emotion/react";
import CssBaseline from "@mui/material/CssBaseline";
import { ThemeProvider } from "@mui/material/styles";
import type { ReactNode } from "react";
import { prefixer } from "stylis";
import rtlPlugin from "stylis-plugin-rtl";

import { theme } from "./theme";

// Emotion cache that flips left/right CSS for right-to-left Hebrew layout.
const rtlCache = createCache({ key: "muirtl", stylisPlugins: [prefixer, rtlPlugin] });

export function RtlThemeProvider({ children }: { children: ReactNode }) {
  return (
    <CacheProvider value={rtlCache}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </CacheProvider>
  );
}
