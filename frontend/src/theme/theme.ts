import { createTheme } from "@mui/material/styles";

export type ColorMode = "light" | "dark";

// Text and coloured controls meet WCAG AA contrast (4.5:1) on both the page background and
// cards, in both modes (checked by scripts/a11y-browser.mjs, once per mode).
const PALETTES = {
  light: {
    primary: { main: "#1e4fd8" },
    secondary: { main: "#0b7a5c" },
    warning: { main: "#b45309" },
    info: { main: "#01579b" },
    text: { secondary: "#5f6368" },
    action: { active: "rgba(0, 0, 0, 0.64)" },
    background: { default: "#f5f7fb" },
  },
  dark: {
    primary: { main: "#8ab4f8" },
    secondary: { main: "#5fd3a8" },
    error: { main: "#ff8a80" },
    warning: { main: "#f6b26b" },
    info: { main: "#7cc4fa" },
    success: { main: "#81c995" },
    text: { secondary: "#b4bac3" },
    background: { default: "#121417", paper: "#1c1f24" },
  },
} as const;

// The phone's status bar colour for the installed app.
export const STATUS_BAR = { light: "#1e4fd8", dark: "#1c1f24" } as const;

export function createAppTheme(mode: ColorMode) {
  return createTheme({
    direction: "rtl",
    palette: { mode, ...PALETTES[mode] },
    typography: {
      fontFamily: '"Heebo", "Arial", sans-serif',
    },
    shape: { borderRadius: 10 },
    components: {
      MuiButton: { defaultProps: { disableElevation: true } },
      // Dark mode lightens raised surfaces with a gradient; plain colours keep contrast exact.
      MuiPaper: { styleOverrides: { root: { backgroundImage: "none" } } },
    },
  });
}

export const theme = createAppTheme("light");
